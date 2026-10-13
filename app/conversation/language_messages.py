"""Small runtime-written chat notices; interface labels remain separate."""

# working, checking, file contents, empty file, truncated, skill on, skill off.
_MESSAGES = {
    "en": ("Working…", "Checking completion…", "Here is the content of {name}:", "{name} is empty.", "The displayed content was truncated by the configured read limit.", "Skill activated: {name}.", "Skill deactivated."),
    "sq": ("Duke punuar…", "Duke kontrolluar përfundimin…", "Përmbajtja e {name}:", "{name} është bosh.", "Përmbajtja u shkurtua sipas kufirit të leximit.", "Aftësia u aktivizua: {name}.", "Aftësia u çaktivizua."),
    "hy": ("Աշխատում եմ…", "Ստուգում եմ ավարտը…", "{name} ֆայլի բովանդակությունը՝", "{name} ֆայլը դատարկ է։", "Բովանդակությունը կրճատվել է ընթերցման սահմանաչափով։", "Հմտությունն ակտիվացված է՝ {name}։", "Հմտությունն անջատված է։"),
    "az": ("İşləyirəm…", "Tamamlanmanı yoxlayıram…", "{name} faylının məzmunu:", "{name} boşdur.", "Məzmun oxuma limitinə görə qısaldılıb.", "Bacarıq aktivləşdirildi: {name}.", "Bacarıq deaktivləşdirildi."),
    "eu": ("Lanean…", "Amaiera egiaztatzen…", "{name} fitxategiaren edukia:", "{name} hutsik dago.", "Edukia irakurketa-mugaren arabera moztu da.", "Trebetasuna aktibatuta: {name}.", "Trebetasuna desaktibatuta."),
    "be": ("Працую…", "Правяраю завяршэнне…", "Змесціва файла {name}:", "{name} пусты.", "Змесціва скарочана праз ліміт чытання.", "Навык уключаны: {name}.", "Навык выключаны."),
    "bs": ("Radim…", "Provjeravam završetak…", "Sadržaj datoteke {name}:", "{name} je prazna.", "Sadržaj je skraćen zbog ograničenja čitanja.", "Vještina je aktivirana: {name}.", "Vještina je deaktivirana."),
    "bg": ("Работя…", "Проверявам завършването…", "Съдържание на {name}:", "{name} е празен.", "Съдържанието е съкратено поради ограничението за четене.", "Умението е активирано: {name}.", "Умението е деактивирано."),
    "ca": ("Treballant…", "Comprovant la finalització…", "Contingut de {name}:", "{name} és buit.", "El contingut s’ha retallat pel límit de lectura.", "Habilitat activada: {name}.", "Habilitat desactivada."),
    "hr": ("Radim…", "Provjeravam dovršetak…", "Sadržaj datoteke {name}:", "{name} je prazna.", "Sadržaj je skraćen zbog ograničenja čitanja.", "Vještina je aktivirana: {name}.", "Vještina je deaktivirana."),
    "cs": ("Pracuji…", "Kontroluji dokončení…", "Obsah souboru {name}:", "{name} je prázdný.", "Obsah byl zkrácen kvůli limitu čtení.", "Dovednost aktivována: {name}.", "Dovednost deaktivována."),
    "da": ("Arbejder…", "Kontrollerer afslutningen…", "Indholdet af {name}:", "{name} er tom.", "Indholdet blev afkortet på grund af læsegrænsen.", "Færdighed aktiveret: {name}.", "Færdighed deaktiveret."),
    "nl": ("Bezig…", "Voltooiing controleren…", "Inhoud van {name}:", "{name} is leeg.", "De inhoud is afgekapt vanwege de ingestelde leeslimiet.", "Vaardigheid geactiveerd: {name}.", "Vaardigheid gedeactiveerd."),
    "et": ("Töötan…", "Kontrollin lõpetamist…", "Faili {name} sisu:", "{name} on tühi.", "Sisu kärbiti lugemispiirangu tõttu.", "Oskus aktiveeritud: {name}.", "Oskus deaktiveeritud."),
    "fi": ("Työskentelen…", "Tarkistan valmistumista…", "Tiedoston {name} sisältö:", "{name} on tyhjä.", "Sisältö katkaistiin lukurajan vuoksi.", "Taito aktivoitu: {name}.", "Taito poistettu käytöstä."),
    "fr": ("En cours…", "Vérification de la réalisation…", "Contenu de {name} :", "{name} est vide.", "Le contenu a été tronqué selon la limite de lecture.", "Compétence activée : {name}.", "Compétence désactivée."),
    "gl": ("Traballando…", "Comprobando a finalización…", "Contido de {name}:", "{name} está baleiro.", "O contido truncouse polo límite de lectura.", "Habilidade activada: {name}.", "Habilidade desactivada."),
    "ka": ("ვმუშაობ…", "ვამოწმებ დასრულებას…", "{name} ფაილის შიგთავსი:", "{name} ცარიელია.", "შიგთავსი შემოკლდა წაკითხვის ლიმიტის გამო.", "უნარი გააქტიურებულია: {name}.", "უნარი გამორთულია."),
    "de": ("In Arbeit…", "Abschluss wird geprüft…", "Inhalt von {name}:", "{name} ist leer.", "Der Inhalt wurde wegen der Lesegrenze gekürzt.", "Fähigkeit aktiviert: {name}.", "Fähigkeit deaktiviert."),
    "el": ("Εργάζομαι…", "Ελέγχω την ολοκλήρωση…", "Περιεχόμενο του {name}:", "Το {name} είναι κενό.", "Το περιεχόμενο περικόπηκε λόγω του ορίου ανάγνωσης.", "Δεξιότητα ενεργοποιήθηκε: {name}.", "Δεξιότητα απενεργοποιήθηκε."),
    "hu": ("Dolgozom…", "A befejezés ellenőrzése…", "A(z) {name} tartalma:", "A(z) {name} üres.", "A megjelenített tartalmat az olvasási korlát miatt csonkoltam.", "Készség aktiválva: {name}.", "Készség kikapcsolva."),
    "is": ("Vinn…", "Athuga verklok…", "Innihald {name}:", "{name} er tóm.", "Efnið var stytt vegna lestrarmarka.", "Færni virkjuð: {name}.", "Færni óvirkjuð."),
    "ga": ("Ag obair…", "Ag seiceáil an chríochnaithe…", "Ábhar {name}:", "Tá {name} folamh.", "Giorraíodh an t-ábhar de réir na teorann léitheoireachta.", "Scil gníomhachtaithe: {name}.", "Scil díghníomhachtaithe."),
    "it": ("Al lavoro…", "Verifica del completamento…", "Contenuto di {name}:", "{name} è vuoto.", "Il contenuto è stato troncato per il limite di lettura.", "Competenza attivata: {name}.", "Competenza disattivata."),
    "lv": ("Strādāju…", "Pārbaudu pabeigšanu…", "Faila {name} saturs:", "{name} ir tukšs.", "Saturs saīsināts lasīšanas ierobežojuma dēļ.", "Prasme aktivizēta: {name}.", "Prasme deaktivizēta."),
    "lt": ("Dirbu…", "Tikrinu užbaigimą…", "Failo {name} turinys:", "{name} yra tuščias.", "Turinys sutrumpintas dėl skaitymo ribos.", "Įgūdis aktyvuotas: {name}.", "Įgūdis išjungtas."),
    "lb": ("Amgaang…", "Ofschloss iwwerpréiwen…", "Inhalt vun {name}:", "{name} ass eidel.", "Den Inhalt gouf wéinst der Lieslimit gekierzt.", "Fäegkeet aktivéiert: {name}.", "Fäegkeet deaktivéiert."),
    "mk": ("Работам…", "Го проверувам завршувањето…", "Содржина на {name}:", "{name} е празна.", "Содржината е скратена поради ограничувањето за читање.", "Вештината е активирана: {name}.", "Вештината е деактивирана."),
    "mt": ("Qed naħdem…", "Qed nivverifika t-tlestija…", "Il-kontenut ta’ {name}:", "{name} huwa vojt.", "Il-kontenut tqassar minħabba l-limitu tal-qari.", "Ħila attivata: {name}.", "Ħila diżattivata."),
    "cnr": ("Radim…", "Provjeravam završetak…", "Sadržaj datoteke {name}:", "{name} je prazna.", "Sadržaj je skraćen zbog ograničenja čitanja.", "Vještina je aktivirana: {name}.", "Vještina je deaktivirana."),
    "nb": ("Arbeider…", "Kontrollerer fullføringen…", "Innholdet i {name}:", "{name} er tom.", "Innholdet ble avkortet på grunn av lesegrensen.", "Ferdighet aktivert: {name}.", "Ferdighet deaktivert."),
    "nn": ("Arbeider…", "Kontrollerer fullføringa…", "Innhaldet i {name}:", "{name} er tom.", "Innhaldet vart avkorta på grunn av lesegrensa.", "Ferdigheit aktivert: {name}.", "Ferdigheit deaktivert."),
    "pl": ("Pracuję…", "Sprawdzam ukończenie…", "Zawartość pliku {name}:", "{name} jest pusty.", "Treść została obcięta z powodu limitu odczytu.", "Umiejętność aktywowana: {name}.", "Umiejętność dezaktywowana."),
    "pt": ("A trabalhar…", "A verificar a conclusão…", "Conteúdo de {name}:", "{name} está vazio.", "O conteúdo foi truncado pelo limite de leitura.", "Competência ativada: {name}.", "Competência desativada."),
    "ro": ("Lucrez…", "Verific finalizarea…", "Conținutul fișierului {name}:", "{name} este gol.", "Conținutul a fost trunchiat din cauza limitei de citire.", "Abilitate activată: {name}.", "Abilitate dezactivată."),
    "ru": ("Работаю…", "Проверяю завершение…", "Содержимое файла {name}:", "{name} пуст.", "Содержимое обрезано из-за ограничения чтения.", "Навык включён: {name}.", "Навык выключен."),
    "gd": ("Ag obair…", "A’ sgrùdadh crìochnachaidh…", "Susbaint {name}:", "Tha {name} falamh.", "Chaidh an t-susbaint a ghiorrachadh air sgàth crìoch leughaidh.", "Sgil air a chur an gnìomh: {name}.", "Sgil air a chur à gnìomh."),
    "sr": ("Радим…", "Проверавам завршетак…", "Садржај датотеке {name}:", "{name} је празна.", "Садржај је скраћен због ограничења читања.", "Вештина је активирана: {name}.", "Вештина је деактивирана."),
    "sk": ("Pracujem…", "Kontrolujem dokončenie…", "Obsah súboru {name}:", "{name} je prázdny.", "Obsah bol skrátený pre limit čítania.", "Zručnosť aktivovaná: {name}.", "Zručnosť deaktivovaná."),
    "sl": ("Delam…", "Preverjam dokončanje…", "Vsebina datoteke {name}:", "{name} je prazna.", "Vsebina je bila skrajšana zaradi omejitve branja.", "Veščina aktivirana: {name}.", "Veščina deaktivirana."),
    "es": ("Trabajando…", "Comprobando la finalización…", "Contenido de {name}:", "{name} está vacío.", "El contenido se ha truncado por el límite de lectura.", "Habilidad activada: {name}.", "Habilidad desactivada."),
    "sv": ("Arbetar…", "Kontrollerar slutförandet…", "Innehållet i {name}:", "{name} är tom.", "Innehållet kortades på grund av läsgränsen.", "Färdighet aktiverad: {name}.", "Färdighet inaktiverad."),
    "tr": ("Çalışıyorum…", "Tamamlanmayı denetliyorum…", "{name} içeriği:", "{name} boş.", "İçerik okuma sınırı nedeniyle kısaltıldı.", "Beceri etkinleştirildi: {name}.", "Beceri devre dışı bırakıldı."),
    "uk": ("Працюю…", "Перевіряю завершення…", "Вміст файлу {name}:", "{name} порожній.", "Вміст скорочено через обмеження читання.", "Навичку ввімкнено: {name}.", "Навичку вимкнено."),
    "cy": ("Wrthi’n gweithio…", "Gwirio cwblhau…", "Cynnwys {name}:", "Mae {name} yn wag.", "Cafodd y cynnwys ei gwtogi oherwydd y terfyn darllen.", "Sgil wedi’i hactifadu: {name}.", "Sgil wedi’i dadactifadu."),
}
_KEYS = ("working", "checking", "contents", "empty", "truncated", "skill_on", "skill_off")
_IMAGES = dict(zip(
    "sq hy az eu be bs bg ca hr cs da nl en et fi fr gl ka de el hu is ga it lv lt lb mk mt cnr nb nn pl pt ro ru gd sr sk sl es sv tr uk cy".split(),
    ("Imazhi u krijua.", "Պատկերը ստեղծված է։", "Şəkil yaradıldı.", "Irudia sortu da.", "Відарыс створаны.",
     "Slika je generisana.", "Изображението е създадено.", "Imatge generada.", "Slika je generirana.",
     "Obrázek byl vytvořen.", "Billedet er genereret.", "Afbeelding gegenereerd.", "Image generated.",
     "Pilt on loodud.", "Kuva luotu.", "Image générée.", "Imaxe xerada.", "სურათი შექმნილია.",
     "Bild erstellt.", "Η εικόνα δημιουργήθηκε.", "A kép elkészült.", "Mynd búin til.", "Íomhá cruthaithe.",
     "Immagine generata.", "Attēls izveidots.", "Vaizdas sukurtas.", "Bild erstallt.", "Сликата е создадена.",
     "L-immaġni nħolqot.", "Slika je generisana.", "Bildet er generert.", "Biletet er generert.",
     "Obraz został wygenerowany.", "Imagem gerada.", "Imagine generată.", "Изображение создано.",
     "Dealbh air a chruthachadh.", "Слика је направљена.", "Obrázok bol vytvorený.", "Slika je ustvarjena.",
     "Imagen generada.", "Bilden har skapats.", "Görsel oluşturuldu.", "Зображення створено.", "Delwedd wedi’i chreu.")
))


def notice(locale, key, **values):
    messages = _MESSAGES.get(locale, _MESSAGES.get("nb") if locale == "no" else None)
    if messages is None:
        # Auto may follow languages outside the dropdown. Keep literal outputs
        # neutral rather than imposing English prose on those languages.
        return values.get("name", "") if key in {"contents", "empty", "skill_on"} else "…"
    return messages[_KEYS.index(key)].format(**values)


def progress_notice(locale, message):
    if locale == "en" or not message:
        return message
    if message == "Checking completion…":
        return notice(locale, "checking")
    # Keep approval/permission notices and operation descriptions literal. A
    # generic "working" label must never hide that a user decision is required.
    if message in {"Preparing your request…", "Thinking…", "Choosing a skill…", "Reading skill guidance…",
                   "Reading attached images…", "Reading attached documents…", "Preparing the next step…",
                   "Saving the conversation…", "Generating image…", "Generating response…",
                   "Preparing cloud attachments…", "Checking cloud attachment context…",
                   "Fitting the reply to cloud capacity…", "Loading local model…"}:
        return notice(locale, "working")
    return message


def image_notice(locale, count):
    if locale == "en":
        return "Image generated." if count == 1 else "Images generated."
    return _IMAGES.get(locale, _IMAGES.get("nb") if locale == "no" else "✓")
