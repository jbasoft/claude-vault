<div align="center">

# 🔐 claude-vault

**Yapay zekâ kodlama ajanınız parolanızın *adını* bilir. Değerini asla.**

[English](../README.md) · [فارسی](README.fa.md) · [العربية](README.ar.md) · [Français](README.fr.md) · **Türkçe** · [Español](README.es.md)

</div>

---

## Sorun

Claude Code ile çalışıyorsunuz. Bir migration çalıştırması, bir API'yi çağırması
ya da bir sunucuya bağlanması gerekiyor. Ve diyor ki:

> *"Veritabanı parolasına ihtiyacım var — siz `.env` dosyanıza ekleyin, ben devam edeyim."*

Buradan sonraki her yol kötü:

| Yaptığınız şey | Olan şey |
|---|---|
| Sohbete yapıştırırsınız | Değer artık dökümde, `~/.claude/projects/` içinde ve model sağlayıcısına giden istekte. Kalıcı olarak. |
| `.env` dosyasına koyarsınız | Ajan dosyayı okur. Aynı sonuç, üstüne bir gün yanlışlıkla commit'lenecek bir dosya. |
| Komutu kendiniz çalıştırırsınız | Artık ajanın elleri sizsiniz. İstediğiniz akış yok oldu. |
| "Geçici olarak" koda gömersiniz | Bunun nasıl bittiğini biliyorsunuz. |

Ajan sırrı reddetmekte haklı. Ama "kendiniz halledin" bir iş akışı değil ve kimse
otuz üretim parolasını aklında tutmaz.

## Çözüm

Kimlik bilgisini ikiye ayırın: ajan **adı** alır, değeri **siz** yazarsınız.

```bash
# Ajan bunu çalıştırır. SİZİN makinenizde bir iletişim kutusu açılır.
vault need DB_PASSWORD

# Ajan bunu çalıştırır. $DB_PASSWORD yalnızca alt süreçte vardır.
vault run DB_PASSWORD -- dotnet ef database update
```

Değer ajanın bağlamından, dökümünden ya da API isteğinden asla geçmez. Ajan ona
hiç sahip olmadı, dolayısıyla sızdıramaz.

## Hızlı başlangıç

```bash
pip install claude-vault        # ya da: pipx install claude-vault
vault install-claude            # skill'i, koruma kancasını ve deny kurallarını kurar
```

Claude Code'u yeniden başlatın. Kurulumun tamamı bu. Bir dahaki sefere kimlik
bilgisine ihtiyaç duyduğunda kasaya kendi gidecek — skill açıklaması 401'lerde,
"missing API key" durumlarında ve kimlik doğrulama kokan her şeyde tetiklenir.

Kendiniz deneyin:

```bash
vault need GITHUB_TOKEN                      # kutu açılır, yazarsınız, biter
vault run GITHUB_TOKEN -- gh auth status     # token var, değer maskeli
vault list                                   # yalnızca adlar, her zaman güvenli
```

---

## Önemli olan dört özellik

### 1. `vault run` — enjekte et, sonra çıktıyı temizle

Sırlar tek bir alt süreç için ortam değişkenine dönüşür. O sürecin yazdığı her
şey dönüş yolunda süzülür — sızıntının gerçekte büründüğü biçimler dâhil: ham,
URL kodlu, base64, JSON kaçışlı ve okuma tamponları arasında bölünmüş hâli.

```bash
vault run STRIPE_SECRET_KEY -- curl -v https://api.stripe.com/v1/charges
# → Authorization: Bearer ***REDACTED:STRIPE_SECRET_KEY***
```

Mesele tam da bu maskeleme: ajan ayrıntılı komutlar çalıştırıp gerçek hata
çıktısını okuyabilir, sır yanında yolculuk etmeden. Değişken adı farklıysa
eşleyin:

```bash
vault run DB_PASSWORD:ConnectionStrings__Default -- dotnet run
```

### 2. `vault need` — ajan sorar, siz kanal dışından yanıtlarsınız

Ajanın çağırmasına izin verilen ve sonucunda bir kimlik bilgisinin var olduğu tek
komut. Adları yazdırır, eksik olanlar için bir kutu açar, siz bitirene kadar
bekler ve iptal ederseniz sıfırdan farklı bir kodla çıkar. Kutuyu kasa sürecinin
kendisi çizer; bastığınız tuşların gidecek başka yeri yoktur.

```bash
vault need DB_PASSWORD SMTP_PASSWORD API_TOKEN --with-username
```

Ekransız CI için `vault set NAME --stdin` var; grafik ortamı olmayan bir terminal
onaylı `getpass` istemine döner.

### 3. `vault template` — git'te kalabilen yapılandırma dosyaları

Sırların commit'lenmesinin asıl nedeni `appsettings.json` dosyasının bir sır
istemesidir. Onun yerine şablonu commit'leyin:

```jsonc
// appsettings.Development.template.json  ← commit'lemesi güvenli
{ "ConnectionStrings": { "Default": "Server=db;Password=${VAULT:DB_PASSWORD}" } }
```

```bash
vault template appsettings.Development.template.json appsettings.Development.json
```

`0600` izinleriyle yazılır ve çıktı gitignore'da değilse sizi uyarır. Her metin
biçimiyle çalışır — `.json`, `.yaml`, `.toml`, `.conf`, `.tfvars`. Bir araç
yalnızca dotenv okuyabiliyorsa, `vault env NAME --to .env.local` dosyayı hiç
yazdırmadan oluşturur.

### 4. Koruma kancası — nezaket değil, zorunluluk

Bir `SKILL.md` modele ne yapacağını söyler. Bir `PreToolUse` kancası bunu gerçek
kılar. `vault install-claude`, bir değeri konuşmaya taşıyabilecek birkaç komutu
engelleyen bir koruma kaydeder:

- `vault get`, `vault env --unsafe-stdout`, `vault run --no-scrub`
- `.env` dosyası, `master.key` veya `secrets.enc` üzerinde `cat`/`Read`
- `echo $DB_PASSWORD`, `printenv`, ortam dökümleri

Engellenen çağrı modele açıklamasını geri verir; model de takılıp kalmak yerine
kendini düzeltip devam eder.

Kanca mevcut `settings.json` dosyanızla birleşir — kendi kancalarınız korunur —
ve beklenmedik her girdide açık biçimde başarısız olur, çünkü iş akışını bozan
bir koruma kaldırılır ve kaldırılmış bir koruma hiçbir şeyi korumaz.

---

## Kutudan çıkan diğer şeyler

**Profiller** — tek kasa, çok ortam:

```bash
vault --profile prod run DB_PASSWORD -- ./migrate.sh
vault --profile staging list
```

**Altı dil**, hem iletişim kutusunda hem CLI'da; Farsça ve Arapça için sağdan
sola yerleşim. Yerel ayarınızdan algılanır ya da siz seçersiniz: `vault lang tr`.

**`vault doctor`** — arka uç, kasa yolu, keyring uygulaması, grafik arayüzün
erişilebilirliği, korumanın kurulu olup olmadığı, dosya izni sorunları.

**Yapılandırılabilir konum** — `VAULT_HOME` kasayı istediğiniz yere koyar:
şifreli bir birim, eşitlenen bir klasör, proje başına bir dizin.

---

## Güvenlik modeli

**Depolama.** Varsa işletim sisteminin kimlik bilgisi deposu (Windows Credential
Manager, macOS Keychain, Secret Service). Yoksa AES-256-GCM ile şifrelenmiş bir
dosya; veri anahtarı Windows'ta DPAPI ile sarmalanır, keyring varsa orada
tutulur, son çare olarak `0600` izinli bir anahtar dosyasına yazılır — bir
uyarıyla birlikte, çünkü bu son durum daha zayıftır ve bunu bilmelisiniz.

Dizin — adlar, türler, notlar, zaman damgaları — bilinçli olarak düz JSON'dur.
Adlar sır değildir ve ajanın onları okuması gerekir.

**Neye karşı korur:** kimlik bilgilerinin bir LLM bağlam penceresine, sohbet
dökümüne, sağlayıcı günlüklerine, kabuk geçmişinize, bir `git commit`'e ya da
ekran paylaşımına girmesine.

**Neye karşı korumaz** — açıkça söylüyorum, çünkü kendini fazla satan bir
güvenlik aracı hiç olmamasından kötüdür:

- Kötü amaçlı yazılım ya da sizin hesabınızla çalışan başka bir süreç. Sizin
  çözebildiğiniz her şeyi o da çözebilir.
- Bilerek çalıştırdığınız ve kendi ortamını dışarı sızdıran bir program.
- Modelin bu kurulumdan **önce** gördüğü bir sır. Onları döndürün.
- Kısıtlanmamış kabuk erişimi olan kararlı bir ajan. Kanca sızıntının maliyetini
  yükseltir; bir kum havuzu değildir.

Bu, **kazara** sızıntıya karşı derinlemesine savunmadır — yani gerçekten olan
sızıntıya karşı.

---

## Katkı

Issue ve PR'lar memnuniyetle karşılanır; özellikle: diğer ajanlar için koruma
kuralları, yeni diller ve temizleyicinin kaçırdığı gerçek sızıntı desenleri.
Gönderebileceğiniz en yararlı şey, o sızıntıyı gösteren başarısız bir testtir.

```bash
git clone https://github.com/jbasoft/claude-vault && cd claude-vault
pip install -e ".[dev]"
pytest -q
```

## Lisans

MIT — [LICENSE](../LICENSE) dosyasına bakın.

---

<div align="center">

Bu araç sizi bir üretim parolasını sohbet penceresine yapıştırmaktan kurtardıysa,
**bir ⭐ hiçbir şeye mal olmaz ve başkalarının bulmasına yardım eder.**

</div>
