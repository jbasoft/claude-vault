<div align="center">

# 🔐 claude-vault

**Tu agente de código conoce el *nombre* de tu contraseña. Nunca su valor.**

[English](../README.md) · [فارسی](README.fa.md) · [العربية](README.ar.md) · [Français](README.fr.md) · [Türkçe](README.tr.md) · **Español**

</div>

---

## El problema

Estás trabajando con Claude Code. Necesita ejecutar una migración, llamar a una
API o entrar en un servidor. Y entonces dice:

> *«Voy a necesitar la contraseña de la base de datos: añádela a tu `.env` y sigo.»*

A partir de ahí, todos los caminos son malos:

| Lo que haces | Lo que sale mal |
|---|---|
| La pegas en el chat | El valor ya está en la transcripción, en `~/.claude/projects/` y en la petición enviada al proveedor del modelo. Para siempre. |
| La pones en `.env` | El agente lee el archivo. Mismo resultado, más un archivo que algún día se commitea por accidente. |
| Ejecutas tú el comando | Te has convertido en las manos del agente. El flujo que querías ha desaparecido. |
| La dejas «temporalmente» en el código | Ya sabes cómo acaba esto. |

El agente hace bien en rechazar el secreto. Pero «apáñatelo tú» no es un flujo de
trabajo, y nadie guarda treinta contraseñas de producción en la cabeza.

## La solución

Parte la credencial en dos: el agente recibe el **nombre**, tú escribes el **valor**.

```bash
# Esto lo ejecuta el agente. Se abre un diálogo en TU máquina.
vault need DB_PASSWORD

# Esto lo ejecuta el agente. $DB_PASSWORD solo existe dentro del proceso hijo.
vault run DB_PASSWORD -- dotnet ef database update
```

El valor nunca pasa por el contexto del agente, por su transcripción ni por la
petición a la API. El agente nunca lo tuvo, así que no puede filtrarlo.

## Inicio rápido

```bash
pip install claude-vault        # o: pipx install claude-vault
vault install-claude            # instala el skill, el hook de guardia y las reglas deny
```

Reinicia Claude Code. Esa es toda la instalación. La próxima vez que necesite una
credencial irá a la bóveda por su cuenta: la descripción del skill se dispara con
los 401, con «missing API key» y con cualquier cosa que huela a autenticación.

Pruébalo tú mismo:

```bash
vault need GITHUB_TOKEN                      # se abre el diálogo, escribes, listo
vault run GITHUB_TOKEN -- gh auth status     # el token está, el valor va oculto
vault list                                   # solo nombres, siempre seguro
```

---

## Cuatro funciones que importan

### 1. `vault run` — inyectar y luego limpiar la salida

Los secretos se convierten en variables de entorno de un único proceso hijo. Todo
lo que ese hijo escribe se filtra a la vuelta, incluidas las formas que adopta una
fuga de verdad: en crudo, codificada en URL, en base64, escapada en JSON e incluso
partida entre dos búferes de lectura.

```bash
vault run STRIPE_SECRET_KEY -- curl -v https://api.stripe.com/v1/charges
# → Authorization: Bearer ***REDACTED:STRIPE_SECRET_KEY***
```

Ese ocultamiento es justo el objetivo: el agente puede ejecutar comandos
detallados y leer los errores reales sin que el secreto viaje con ellos. Si el
nombre de la variable es otro, remapéalo:

```bash
vault run DB_PASSWORD:ConnectionStrings__Default -- dotnet run
```

### 2. `vault need` — el agente pregunta, tú respondes fuera del canal

El único comando que el agente puede llamar y cuyo resultado es que la credencial
exista. Imprime nombres, abre un diálogo para lo que falte, espera a que termines
y sale con código distinto de cero si cancelas. El diálogo lo dibuja el propio
proceso de la bóveda, así que las teclas que pulsas no tienen otro sitio adonde ir.

```bash
vault need DB_PASSWORD SMTP_PASSWORD API_TOKEN --with-username
```

Para CI sin pantalla está `vault set NAME --stdin`; una terminal sin entorno
gráfico recurre a una petición `getpass` con confirmación.

### 3. `vault template` — archivos de configuración que siguen en git

Si los secretos acaban commiteados es porque `appsettings.json` pide uno.
Commitea la plantilla en su lugar:

```jsonc
// appsettings.Development.template.json  ← seguro de commitear
{ "ConnectionStrings": { "Default": "Server=db;Password=${VAULT:DB_PASSWORD}" } }
```

```bash
vault template appsettings.Development.template.json appsettings.Development.json
```

Se escribe con permisos `0600` y te avisa si la salida no está en el gitignore.
Funciona con cualquier formato de texto: `.json`, `.yaml`, `.toml`, `.conf`,
`.tfvars`. Cuando una herramienta solo lee dotenv,
`vault env NAME --to .env.local` escribe el archivo sin imprimirlo nunca.

### 4. El hook de guardia — obligación, no cortesía

Un `SKILL.md` le dice al modelo qué hacer. Un hook `PreToolUse` hace que sea
cierto. `vault install-claude` registra una guardia que bloquea el puñado de
comandos capaces de meter un valor en la conversación:

- `vault get`, `vault env --unsafe-stdout`, `vault run --no-scrub`
- `cat`/`Read` sobre un archivo `.env`, `master.key` o `secrets.enc`
- `echo $DB_PASSWORD`, `printenv`, volcados de entorno

Una llamada bloqueada devuelve su explicación al modelo, que se corrige y sigue en
lugar de quedarse atascado.

El hook se fusiona con tu `settings.json` existente —tus propios hooks se
conservan— y deja pasar cualquier entrada inesperada, porque una guardia que rompe
flujos de trabajo se termina desinstalando, y una guardia desinstalada no protege
nada.

---

## También incluido

**Perfiles**: una bóveda, varios entornos.

```bash
vault --profile prod run DB_PASSWORD -- ./migrate.sh
vault --profile staging list
```

**Seis idiomas**, en el diálogo y en la CLI, con disposición de derecha a
izquierda para persa y árabe. Se detecta desde tu locale o lo eliges:
`vault lang es`.

**`vault doctor`**: backend, ruta de la bóveda, implementación de keyring, si la
interfaz gráfica está disponible, si la guardia está instalada y problemas de
permisos.

**Ubicación configurable**: `VAULT_HOME` coloca la bóveda donde quieras: un
volumen cifrado, una carpeta sincronizada, un directorio por proyecto.

---

## Modelo de seguridad

**Almacenamiento.** El almacén de credenciales del sistema cuando existe (Windows
Credential Manager, Llavero de macOS, Secret Service). Si no, un archivo cifrado
con AES-256-GCM cuya clave de datos se envuelve con DPAPI en Windows, se guarda en
el keyring donde lo haya, o se escribe como último recurso en un archivo de clave
con permisos `0600` —con un aviso, porque ese último caso es más débil y debes
saberlo.

El índice —nombres, tipos, notas, marcas de tiempo— es JSON en claro a propósito.
Los nombres no son secretos y el agente necesita leerlos.

**Contra qué protege:** contra que una credencial entre en la ventana de contexto
de un LLM, en una transcripción de chat, en los registros de un proveedor, en tu
historial de shell, en un `git commit` o en una pantalla compartida.

**Contra qué no protege** —dicho sin rodeos, porque una herramienta de seguridad
que promete de más es peor que ninguna:

- Malware o cualquier otro proceso que se ejecute como tú. Todo lo que tú puedas
  descifrar, él también.
- Un programa que ejecutas a propósito y que exfiltra su propio entorno.
- Un secreto que el modelo vio **antes** de instalar esto. Rótalo.
- Un agente decidido con acceso irrestricto a la shell. El hook encarece la fuga;
  no es un sandbox.

Esto es defensa en profundidad para la fuga **accidental**, que es la que de
verdad ocurre.

---

## Contribuir

Se agradecen issues y PR, sobre todo: reglas de guardia para otros agentes,
traducciones y patrones reales de fuga que el limpiador no detecte. Lo más útil
que puedes enviar es un test que falle con esa fuga.

```bash
git clone https://github.com/jbasoft/claude-vault && cd claude-vault
pip install -e ".[dev]"
pytest -q
```

## Licencia

MIT — ver [LICENSE](../LICENSE).

---

<div align="center">

Si esto te ha librado de pegar una contraseña de producción en una ventana de chat,
**una ⭐ no cuesta nada y ayuda a que otros lo encuentren.**

</div>
