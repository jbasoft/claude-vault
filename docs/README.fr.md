<div align="center">

# 🔐 claude-vault

**Votre agent de code connaît le *nom* de votre mot de passe. Jamais sa valeur.**

[English](../README.md) · [فارسی](README.fa.md) · [العربية](README.ar.md) · **Français** · [Türkçe](README.tr.md) · [Español](README.es.md)

</div>

---

## Le problème

Vous travaillez avec Claude Code. Il doit lancer une migration, appeler une API,
se connecter à un serveur. Alors il dit :

> *« J'ai besoin du mot de passe de la base — ajoutez-le à votre `.env` et je continue. »*

À partir de là, tous les chemins sont mauvais :

| Ce que vous faites | Ce qui se passe |
|---|---|
| Vous le collez dans le chat | La valeur est désormais dans la transcription, dans `~/.claude/projects/` et dans la requête envoyée au fournisseur du modèle. Définitivement. |
| Vous le mettez dans `.env` | L'agent lit le fichier. Même résultat, plus un fichier qui finira committé par accident. |
| Vous lancez la commande vous-même | Vous êtes devenu les mains de l'agent. Le flux de travail que vous vouliez a disparu. |
| Vous le codez en dur « provisoirement » | Vous savez comment cela finit. |

L'agent a raison de refuser le secret. Mais « débrouillez-vous » n'est pas un
flux de travail, et personne ne garde trente mots de passe de production en tête.

## La solution

Coupez l'identifiant en deux : l'agent reçoit le **nom**, vous tapez la **valeur**.

```bash
# L'agent lance ceci. Une boîte de dialogue s'ouvre sur VOTRE machine.
vault need DB_PASSWORD

# L'agent lance ceci. $DB_PASSWORD n'existe que dans le processus enfant.
vault run DB_PASSWORD -- dotnet ef database update
```

La valeur ne passe jamais par le contexte de l'agent, sa transcription ou la
requête API. L'agent ne l'a jamais eue, il ne peut donc pas la divulguer.

## Démarrage rapide

```bash
pip install claude-vault        # ou : pipx install claude-vault
vault install-claude            # installe le skill, le hook de garde et les règles deny
```

Redémarrez Claude Code. C'est toute l'installation. La prochaine fois qu'il aura
besoin d'un identifiant, il ira au coffre de lui-même — la description du skill
se déclenche sur les 401, les « missing API key » et tout ce qui sent
l'authentification.

Essayez vous-même :

```bash
vault need GITHUB_TOKEN                      # le dialogue s'ouvre, vous tapez, c'est fini
vault run GITHUB_TOKEN -- gh auth status     # le jeton est là, la valeur est masquée
vault list                                   # les noms seuls, toujours sans risque
```

---

## Quatre fonctionnalités qui comptent

### 1. `vault run` — injecter, puis nettoyer la sortie

Les secrets deviennent des variables d'environnement pour un seul processus
enfant. Tout ce que cet enfant écrit est filtré au retour, y compris sous les
formes que prend réellement une fuite : brut, URL-encodé, base64, échappé en
JSON, et même coupé entre deux tampons de lecture.

```bash
vault run STRIPE_SECRET_KEY -- curl -v https://api.stripe.com/v1/charges
# → Authorization: Bearer ***REDACTED:STRIPE_SECRET_KEY***
```

C'est tout l'intérêt : l'agent peut lancer des commandes verbeuses et lire les
vraies erreurs sans que le secret voyage avec. Renommez la variable au besoin :

```bash
vault run DB_PASSWORD:ConnectionStrings__Default -- dotnet run
```

### 2. `vault need` — l'agent demande, vous répondez hors canal

La seule commande que l'agent a le droit d'appeler et dont le résultat est
l'existence d'un identifiant. Elle affiche les noms, ouvre un dialogue pour ce
qui manque, attend que vous ayez fini, et sort avec un code non nul si vous
annulez. Le dialogue est dessiné par le processus du coffre : les frappes n'ont
nulle part ailleurs où aller.

```bash
vault need DB_PASSWORD SMTP_PASSWORD API_TOKEN --with-username
```

Pour une CI sans écran, `vault set NAME --stdin` ; un terminal sans affichage
graphique retombe sur une invite `getpass` avec confirmation.

### 3. `vault template` — des fichiers de config qui restent dans git

Si des secrets finissent committés, c'est parce qu'`appsettings.json` en réclame
un. Committez plutôt un modèle :

```jsonc
// appsettings.Development.template.json  ← committable sans risque
{ "ConnectionStrings": { "Default": "Server=db;Password=${VAULT:DB_PASSWORD}" } }
```

```bash
vault template appsettings.Development.template.json appsettings.Development.json
```

Écrit avec les permissions `0600`, et vous prévient si la sortie n'est pas dans
le `.gitignore`. Fonctionne avec tout format texte — `.json`, `.yaml`, `.toml`,
`.conf`, `.tfvars`. Quand un outil ne lit que du dotenv,
`vault env NAME --to .env.local` écrit le fichier sans jamais l'afficher.

### 4. Le hook de garde — de la contrainte, pas de la politesse

Un `SKILL.md` dit au modèle quoi faire. Un hook `PreToolUse` le rend vrai.
`vault install-claude` enregistre une garde qui bloque la poignée de commandes
susceptibles de faire entrer une valeur dans la conversation :

- `vault get`, `vault env --unsafe-stdout`, `vault run --no-scrub`
- `cat`/`Read` sur un fichier `.env`, `master.key` ou `secrets.enc`
- `echo $DB_PASSWORD`, `printenv`, les vidages d'environnement

Un appel bloqué renvoie son explication au modèle, qui se corrige et poursuit au
lieu de rester bloqué.

Le hook fusionne avec votre `settings.json` existant — vos propres hooks sont
conservés — et laisse passer tout ce qui est inattendu : une garde qui casse les
flux de travail finit désinstallée, et une garde désinstallée ne protège rien.

---

## Également inclus

**Profils** — un coffre, plusieurs environnements :

```bash
vault --profile prod run DB_PASSWORD -- ./migrate.sh
vault --profile staging list
```

**Six langues**, dialogue et CLI, avec mise en page de droite à gauche pour le
persan et l'arabe. Détectée depuis votre locale, ou choisie : `vault lang fr`.

**`vault doctor`** — backend, chemin du coffre, implémentation keyring,
disponibilité de l'interface graphique, présence de la garde, problèmes de
permissions.

**Emplacement configurable** — `VAULT_HOME` place le coffre où vous voulez : un
volume chiffré, un dossier synchronisé, un répertoire par projet.

---

## Modèle de sécurité

**Stockage.** Le gestionnaire d'identifiants du système quand il existe (Windows
Credential Manager, trousseau macOS, Secret Service). Sinon un fichier chiffré
en AES-256-GCM dont la clé de données est enveloppée par DPAPI sous Windows,
gardée dans le trousseau là où il y en a un, ou écrite en dernier recours dans un
fichier de clé en `0600` — avec un avertissement, parce que ce dernier cas est
plus faible et que vous devez le savoir.

L'index — noms, types, notes, horodatages — est du JSON en clair, volontairement.
Les noms ne sont pas secrets et l'agent doit pouvoir les lire.

**Ce que cela protège :** l'entrée d'un identifiant dans la fenêtre de contexte
d'un LLM, une transcription de chat, les journaux d'un fournisseur, votre
historique shell, un `git commit`, un partage d'écran.

**Ce que cela ne protège pas** — dit franchement, car un outil de sécurité qui
promet trop vaut moins que rien :

- Un logiciel malveillant ou tout processus tournant sous votre compte. Ce que
  vous pouvez déchiffrer, il le peut.
- Un programme que vous lancez délibérément et qui exfiltre son environnement.
- Un secret que le modèle a vu **avant** cette installation. Faites-le tourner.
- Un agent déterminé disposant d'un shell sans restriction. Le hook augmente le
  coût d'une fuite ; ce n'est pas un bac à sable.

C'est une défense en profondeur contre la fuite **accidentelle**, celle qui
arrive vraiment.

---

## Contribuer

Issues et PR bienvenues, en particulier : règles de garde pour d'autres agents,
traductions, et schémas de fuite réels que le nettoyeur laisse passer. Le plus
utile que vous puissiez envoyer est un test qui échoue sur cette fuite.

```bash
git clone https://github.com/jbasoft/claude-vault && cd claude-vault
pip install -e ".[dev]"
pytest -q
```

## Licence

MIT — voir [LICENSE](../LICENSE).

---

<div align="center">

Si cet outil vous a évité de coller un mot de passe de production dans un chat,
**une ⭐ ne coûte rien et aide les autres à le trouver.**

</div>
