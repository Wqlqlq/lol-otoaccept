## İndir ve çalıştır

1. Aşağıdaki **Assets** bölümünden **`LoLAutoAccept.exe`** dosyasını indir.
2. Exe'yi kendine ait bir klasöre koy (ör. `Belgeler\LoLAutoAccept`). Ayarlar (`config.json`),
   loglar (`logs.txt`) ve template (`assets\accept_template.png`) exe'nin yanına kaydedilir.
3. Çift tıklayarak aç. Python kurmana gerek yok. İlk açılış birkaç saniye sürebilir.

**"Windows kişisel bilgisayarınızı korudu" uyarısı çıkarsa:** **Ek bilgi** → **Yine de çalıştır**.
Exe dijital olarak imzalı olmadığı için Windows bu uyarıyı gösterir. Program global kısayol
tuşunu (F8) dinlediği ve mouse tıklaması yaptığı için bazı antivirüs programları da yanlış alarm
verebilir. Exe, bu depodaki açık kaynak koddan GitHub Actions ile derlendi; aşağıdaki SHA256
değeriyle indirdiğin dosyayı doğrulayabilirsin.

## İlk ayar

1. Sıradayken maç bulununca uygulamaya geç, **Capture Template**'e bas ve ACCEPT butonunun
   etrafına sıkı bir kutu çiz (ekran donar, acele etme).
2. **Select Area** ile butonun çıktığı bölgeyi biraz geniş seç.
3. **Select Click Point** ile butonun ortasına tıkla.
4. **Start Monitoring**'e veya **F8**'e bas.

- **F8:** Monitoring aç/kapat (oyun penceresi açıkken de çalışır)
- **ESC / sağ tık:** Seçim ekranından çık

Ayrıntılı kullanım ve sorun giderme için depodaki README'ye bak.
Program yalnızca ekran görüntüsü alır ve normal mouse tıklaması yapar; oyunun dosyalarına,
belleğine, API'sine veya process'ine dokunmaz.
