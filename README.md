# LoL Auto Accept

League of Legends istemcisinde maç bulunduğunda çıkan **ACCEPT / KABUL ET** butonunu ekran
görüntüsünden algılayıp, önceden seçtiğin noktaya **bir kez** mouse tıklaması yapan basit bir
Windows masaüstü uygulaması.

Uygulama yalnızca iki şey yapar:

- Ekranın seçtiğin bölgesinin ekran görüntüsünü alır (OpenCV template matching ile karşılaştırır).
- Normal bir mouse tıklaması simüle eder (`pyautogui.click`).

Oyunun dosyalarına, belleğine, API'sine (LCU) veya process'ine **hiçbir şekilde** dokunmaz.

---

## Gereksinimler

- Windows 10 veya Windows 11
- Python 3.10 veya daha yeni bir sürüm

## 1. Python kurulumu

1. <https://www.python.org/downloads/windows/> adresinden güncel Python 3 sürümünü indir.
2. Kurulumun ilk ekranında **"Add python.exe to PATH"** kutusunu işaretle, sonra
   **Install Now** de.
3. Yeni bir Komut İstemi (cmd) veya PowerShell aç ve kontrol et:

   ```bat
   python --version
   ```

   `Python 3.10` veya üzeri bir sürüm görmelisin.

## 2. Bağımlılıkların kurulumu

Proje klasöründe (bu README'nin olduğu yerde) şunu çalıştır:

```bat
pip install -r requirements.txt
```

İstersen önce sanal ortam (virtual environment) oluşturabilirsin:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Kurulan paketler: `opencv-python`, `numpy`, `Pillow`, `pyautogui`, `pynput`.
(`tkinter`, Windows için Python kurulumuyla birlikte gelir.)

## 3. Uygulamayı çalıştırma

```bat
python main.py
```

"LoL Auto Accept" penceresi açılır. Ayarlar `config.json` dosyasına kaydedilir ve uygulama
bir sonraki açılışta otomatik olarak yükler.

---

## Kullanım

Üç şeyi bir kez ayarlaman yeterli: **Detection Area**, **Template Image** ve **Click Position**.
Bunları seçerken LoL istemcisinin her zamanki boyutunda ve konumunda açık olması gerekir.

Seçim ekranlarının hepsinde ekranın o anki görüntüsü **dondurulur** ve karartılır, yani
acele etmene gerek yok. Seçimden vazgeçmek için **ESC** tuşuna bas ya da **sağ tıkla**.

### Detection Area nasıl seçilir

1. **Select Area** butonuna bas. Ana pencere gizlenir ve ekran karartılır.
2. Mouse ile, maç bulunduğunda **ACCEPT butonunun çıktığı bölgeyi** içine alan bir dikdörtgen
   çiz. Butondan biraz daha geniş bir alan seçmek iyidir.
3. Seçilen alan ana pencerede gösterilir, örneğin: `x=700  y=350  width=500  height=400`.

Bölge ne kadar küçük olursa kontrol o kadar hızlı olur. Ama template'ten küçük olamaz.

### Template nasıl alınır

Template, programın ekranda arayacağı görseldir (ACCEPT butonunun kendisi).

1. Maç bulundu penceresi ekrandayken (ör. sıradayken maç bulunduğunda) uygulamaya geç ve
   **Capture Template** butonuna bas. Ekran anında dondurulduğu için popup kapansa bile
   seçimi rahatça yapabilirsin.
2. **ACCEPT** butonunun etrafına sıkı bir dikdörtgen çiz.
3. Görsel `assets/accept_template.png` olarak kaydedilir ve ana pencerede küçük bir önizlemesi
   gösterilir.

İpuçları:

- Template'i mouse butonun **üzerinde değilken** al. Hover efekti görüntüyü değiştirir.
- Template mutlaka Detection Area'dan küçük olmalı (aksi halde uyarı verilir).
- İstemci dilini, çözünürlüğünü veya pencere boyutunu değiştirirsen template'i yeniden al.
- `assets/accept_template.png` depoda hazır gelmez. Butonun görüntüsü çözünürlüğe ve dile
  göre değiştiği için kendi ekranından yakalaman gerekir.

### Click Position nasıl seçilir

1. **Select Click Point** butonuna bas.
2. Ekranda bir artı işareti (crosshair) ve koordinatlar görünür.
3. Maç bulunduğunda tıklanacak noktaya, yani ACCEPT butonunun ortasına **bir kez tıkla**.
4. Koordinat kaydedilir, örneğin: `x=960  y=620`.

### Detection Threshold ve Check Interval

- **Detection Threshold** (varsayılan `0.90`): Eşleşme için gereken minimum benzerlik
  (0.50–1.00). Yanlış tıklama oluyorsa yükselt. Buton görünürken algılanmıyorsa
  (Confidence değeri eşiğin altında kalıyorsa) `0.80–0.85`'e düşür veya template'i yeniden al.
- **Check Interval** (varsayılan `300` ms): Ekranın ne sıklıkla kontrol edileceği (50–5000 ms).

### Monitoring

- **Start Monitoring** ile izleme başlar. İzleme ayrı bir thread'de çalışır, arayüz donmaz.
- Her kontrolde sadece Detection Area'nın ekran görüntüsü alınır ve
  `cv2.matchTemplate(..., cv2.TM_CCOEFF_NORMED)` ile en yüksek benzerlik (confidence) bulunur.
- Sağdaki **Preview** alanında son görüntü ve anlık **Confidence** değeri görünür. Eşleşme
  bulunduğunda bulunan yer yeşil bir çerçeveyle işaretlenir.
- İzleme sırasında ayar butonları kilitlenir. Değiştirmek için önce izlemeyi durdur.

Status değerleri:

| Status           | Anlamı                                                   |
| ---------------- | -------------------------------------------------------- |
| `Idle`           | İzleme kapalı                                            |
| `Monitoring`     | Ekran izleniyor, buton bekleniyor                        |
| `Match detected` | Buton algılandı (confidence ≥ threshold)                 |
| `Clicked`        | Tıklama yapıldı; butonun ekrandan kaybolması bekleniyor  |

### Spam tıklama koruması

Buton ekranda birkaç saniye kalabildiği için program sürekli tıklamaz. Basit bir cooldown
yerine bir durum makinesi (state machine) kullanılır:

```
WAITING ──(confidence ≥ threshold)──> DETECTED ──(tıkla)──> WAIT_FOR_DISAPPEAR
WAIT_FOR_DISAPPEAR ──(confidence < threshold)──> WAITING
```

Tıklamadan sonra yeni bir tıklama için butonun önce ekrandan **kaybolması** gerekir. Tek
karelik bir titremenin tekrar tıklatmaması için kaybolma, art arda 3 kontrolde eşiğin altında
kalmasıyla onaylanır. Böylece kabul ettiğin maç bozulup yeni bir maç bulunduğunda program
yeniden tıklar, ama aynı popup için asla ikinci kez tıklamaz.

---

## Kısayol tuşları

| Tuş                    | Görevi                                                                 |
| ---------------------- | ---------------------------------------------------------------------- |
| **F8**                 | Monitoring'i açar / kapatır. Oyun penceresi aktifken de çalışır (global). |
| **ESC**                | Sadece aktif bir seçim ekranı varsa seçimden çıkar. Programı kapatmaz. |
| **Sağ tık**            | Seçim ekranındayken seçimi iptal eder.                                 |

Kısayollar `pynput` ile dinlenir ve tuşlar engellenmez: oyun ve diğer programlar tuşları
normal şekilde almaya devam eder.

---

## Ayarlar: `config.json`

Seçtiğin her şey otomatik kaydedilir:

```json
{
  "detection_region": {
    "x": 700,
    "y": 350,
    "width": 500,
    "height": 400
  },
  "click_position": {
    "x": 960,
    "y": 620
  },
  "threshold": 0.9,
  "check_interval_ms": 300,
  "template_path": "assets/accept_template.png"
}
```

Dosya bozulursa uygulama uyarı verir, varsayılan ayarlarla açılır ve bir sonraki kayıtta
dosyayı düzeltir.

## Loglar: `logs.txt`

Olaylar `logs.txt` dosyasına yazılır:

```
22:14:01 Monitoring started
22:16:32 Template detected confidence=0.94
22:16:32 Clicked x=960 y=620
22:16:36 Template disappeared
22:20:15 Monitoring stopped
```

---

## Sorun giderme

- **Buton görünürken algılanmıyor:** Preview'da butonun göründüğünü kontrol et. Detection
  Area'nın üstünde başka bir pencere olmamalı, **bu uygulamanın penceresi de dahil**.
  Confidence düşükse threshold'u biraz düşür veya template'i yeniden al.
- **Tıklama ya da F8 oyun açıkken çalışmıyor:** LoL istemcisi yönetici olarak çalışıyorsa
  Windows, normal yetkideki programların ona tıklama göndermesini engeller. Bu durumda
  Komut İstemi'ni **Yönetici olarak** açıp `python main.py` ile başlat.
- **"PyAutoGUI fail-safe" hatası:** Tıklama anında mouse ekranın bir köşesindeyse PyAutoGUI
  güvenlik için işlemi durdurur. Bu bir acil durdurma özelliğidir. İzlemeyi yeniden başlat.
- **Koordinatlar kayık:** Windows ekran ölçeklendirmesi (%125, %150) desteklenir, uygulama
  gerçek piksel koordinatlarıyla çalışır. Ölçeklendirmeyi veya çözünürlüğü değiştirdiysen
  alanı, template'i ve tıklama noktasını yeniden seç.
- **Birden fazla monitör:** Seçim ve algılama **ana (primary) monitörde** yapılır. LoL
  istemcisini ana monitörde aç.

---

## Dosya yapısı

```
lol-otoaccept/
├── main.py              # Ana pencere (tkinter), uygulamanın giriş noktası
├── detector.py          # Template matching, state machine, monitoring thread'i
├── screen_selector.py   # Tam ekran alan / nokta seçim ekranı
├── config_manager.py    # config.json okuma/yazma ve ayar veri tipleri
├── hotkeys.py           # Global kısayol tuşları (F8 / ESC), pynput ile
├── logger.py            # logs.txt loglama
├── config.json          # Kaydedilmiş ayarlar
├── requirements.txt
├── README.md
└── assets/
    └── accept_template.png   # "Capture Template" ile oluşturulur
```

## Uyarı

Bu araç yalnızca ekran görüntüsü ve normal mouse tıklaması kullanır. Yine de üçüncü parti
araç kullanımı oyunun kullanım koşullarına tabidir. Kullanım sorumluluğu kullanıcıya aittir.
