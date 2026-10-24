**Türkçe** · English version below

## İndir ve çalıştır

1. Aşağıdaki **Assets** bölümünden **`LoLAutoAccept.exe`** dosyasını indir.
2. Exe'yi kendine ait bir klasöre koy (ör. `Belgeler\LoLAutoAccept`). Ayarlar (`config.json`),
   loglar (`logs.txt`) ve template (`assets\accept_template.png`) exe'nin yanına kaydedilir.
3. Çift tıklayarak aç. Python kurmana gerek yok. İlk açılış birkaç saniye sürebilir.

**"Windows kişisel bilgisayarınızı korudu" uyarısı çıkarsa:** **Ek bilgi** → **Yine de çalıştır**.
Exe dijital olarak imzalı olmadığı için Windows bu uyarıyı gösterir. Program global kısayol
tuşunu (F8) dinlediği ve mouse tıklaması yaptığı için bazı antivirüs programları da yanlış alarm
verebilir. Exe, bu depodaki açık kaynak koddan GitHub Actions ile derlendi; en alttaki SHA256
değeriyle indirdiğin dosyayı doğrulayabilirsin.

## İlk ayar

1. Sıradayken maç bulununca uygulamaya geç, **Capture Template**'e bas ve ACCEPT butonunun
   etrafına sıkı bir kutu çiz (ekran donar, acele etme).
2. **Select Area** ile butonun çıktığı bölgeyi biraz geniş seç.
3. **Select Click Point** ile butonun ortasına tıkla.
4. **Start Monitoring**'e veya **F8**'e bas.

- **F8:** Monitoring aç/kapat (oyun penceresi açıkken de çalışır)
- **ESC / sağ tık:** Seçim ekranından çık

Ayrıntılı kullanım ve sorun giderme için depodaki [README](https://github.com/Wqlqlq/lol-otoaccept/blob/claude/gallant-pasteur-6ueve7/README.md)'ye bak.
Program yalnızca ekran görüntüsü alır ve normal mouse tıklaması yapar; oyunun dosyalarına,
belleğine, API'sine veya process'ine dokunmaz.

---

**English**

## Download and run

1. Download **`LoLAutoAccept.exe`** from the **Assets** section below.
2. Put the exe in a folder of its own (e.g. `Documents\LoLAutoAccept`). Settings (`config.json`),
   logs (`logs.txt`) and the template (`assets\accept_template.png`) are saved next to the exe.
3. Double-click to open it. No Python installation needed. The first start may take a few
   seconds.

**If you see "Windows protected your PC":** click **More info** → **Run anyway**.
Windows shows this warning because the exe is not digitally signed. Since the app listens for a
global hotkey (F8) and performs mouse clicks, some antivirus programs may also raise a false
alarm. The exe was built from the open source code in this repository by GitHub Actions; you
can verify the downloaded file with the SHA256 hash at the bottom.

## First-time setup

1. When a match is found while you are in queue, switch to the app, click **Capture Template**
   and drag a tight box around the ACCEPT button (the screen freezes, no need to hurry).
2. With **Select Area**, select the region where the button appears, a bit larger than it.
3. With **Select Click Point**, click the center of the button.
4. Click **Start Monitoring** or press **F8**.

- **F8:** Start / stop monitoring (works while the game window is open)
- **ESC / right-click:** Leave the selection screen

See the [README](https://github.com/Wqlqlq/lol-otoaccept/blob/claude/gallant-pasteur-6ueve7/README.en.md)
in the repository for detailed usage and troubleshooting.
The app only takes screenshots and performs normal mouse clicks; it never touches the game's
files, memory, API or process.
