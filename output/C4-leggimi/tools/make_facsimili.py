# -*- coding: utf-8 -*-
"""Generate the two INVENTED sample documents used by the demo (static/esempi/).

Both images are fake by design:
* every name, address and number is invented and labelled as such;
* access codes and file numbers are covered with black bars (never printed);
* a large "FAC-SIMILE - ESEMPIO INVENTATO" header and diagonal watermark.
No logos or official graphics are drawn.

Run:  python tools/make_facsimili.py
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "esempi"
FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/Library/Fonts")]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    names = (["arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold
             else ["arial.ttf", "DejaVuSans.ttf", "Arial.ttf"])
    for d in FONT_DIRS:
        for n in names:
            p = d / n
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)


W, H = 1100, 1500
RED = (190, 20, 20)


def base_sheet(title_band: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), (250, 248, 242))
    d = ImageDraw.Draw(img)
    # Red band at the top: impossible to miss
    d.rectangle([0, 0, W, 110], fill=RED)
    d.text((W // 2, 55), "FAC-SIMILE - ESEMPIO INVENTATO", font=font(54, True), fill="white", anchor="mm")
    d.text((W // 2, 140), title_band, font=font(24, True), fill=RED, anchor="mm")
    return img, d


def watermark(img: Image.Image) -> Image.Image:
    layer = Image.new("RGBA", (W * 2, H * 2), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    f = font(92, True)
    for i in range(6):
        ld.text((W, 300 + i * 520), "FAC-SIMILE  ESEMPIO INVENTATO", font=f, fill=(200, 30, 30, 70), anchor="mm")
    layer = layer.rotate(32, resample=Image.BICUBIC).crop((W // 2, H // 2, W // 2 + W, H // 2 + H))
    out = img.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")


def covered(d: ImageDraw.ImageDraw, x: int, y: int, w: int, label: str = "COPERTO") -> None:
    d.rectangle([x, y - 4, x + w, y + 34], fill=(10, 10, 10))
    d.text((x + w // 2, y + 15), label, font=font(18, True), fill=(255, 255, 255), anchor="mm")


def field(d: ImageDraw.ImageDraw, y: int, label: str, value: str, vsize: int = 30) -> int:
    d.text((70, y), label, font=font(22), fill=(70, 70, 70))
    d.text((70, y + 30), value, font=font(vsize, True), fill=(15, 15, 15))
    return y + 30 + vsize + 26


def photo_look(img: Image.Image, seed: int) -> Image.Image:
    """Slight rotation, blur and vignetting so it looks like a phone photo."""
    random.seed(seed)
    bg = Image.new("RGB", (W + 160, H + 160), (96, 84, 70))
    bg.paste(img.filter(ImageFilter.GaussianBlur(0.6)), (80, 80))
    bg = bg.rotate(random.choice([-1.6, 1.3]), resample=Image.BICUBIC, fillcolor=(96, 84, 70))
    return bg.resize(((W + 160) * 3 // 4, (H + 160) * 3 // 4), Image.LANCZOS)


def ricevuta_poste() -> Image.Image:
    img, d = base_sheet("Ricevuta di esempio - non è un documento di Poste Italiane")
    y = 190
    d.text((70, y), "UFFICIO POSTALE MILANO 99 (inventato) - Sportello Amico", font=font(28, True), fill=(20, 20, 60))
    y += 48
    d.text((70, y), "RICEVUTA DI PRESENTAZIONE DELLA RICHIESTA", font=font(34, True), fill=(0, 0, 0))
    y += 44
    d.text((70, y), "DI RILASCIO DEL PERMESSO DI SOGGIORNO", font=font(34, True), fill=(0, 0, 0))
    y += 70
    d.line([70, y, W - 70, y], fill=(0, 0, 0), width=2)
    y += 24
    y = field(d, y, "Data di accettazione", "29/09/2026  ore 10:42")
    y = field(d, y, "Richiedente (nome inventato)", "ROSA ESEMPIO")
    y = field(d, y, "Cittadinanza", "FILIPPINE")
    y = field(d, y, "Tipo di richiesta", "PRIMO RILASCIO - LAVORO SUBORDINATO")
    d.text((70, y), "Numero assicurata / pratica", font=font(22), fill=(70, 70, 70))
    covered(d, 70, y + 34, 420, "NUMERO COPERTO NEL FAC-SIMILE")
    y += 100
    d.rectangle([60, y - 10, W - 60, y + 190], outline=(0, 0, 0), width=2)
    d.text((80, y + 4), "Codici per consultare la pratica sul Portale Immigrazione", font=font(24, True), fill=(0, 0, 0))
    d.text((80, y + 52), "USER ID", font=font(24), fill=(0, 0, 0))
    covered(d, 260, y + 50, 560, "CODICE COPERTO - NON ESTRARRE")
    d.text((80, y + 112), "PASSWORD", font=font(24), fill=(0, 0, 0))
    covered(d, 260, y + 110, 560, "CODICE COPERTO - NON ESTRARRE")
    y += 230
    d.text((70, y), "Convocazione per i rilievi fotodattiloscopici:", font=font(24, True), fill=(0, 0, 0))
    y += 38
    d.text((70, y), "12/01/2027 ore 09:20 - Questura di Milano, Ufficio Immigrazione", font=font(26, True), fill=(0, 0, 0))
    y += 36
    d.text((70, y), "(data inventata; la sede è indicata nella lettera di convocazione)", font=font(20), fill=(70, 70, 70))
    y += 60
    d.text((70, y), "Conservare con cura la presente ricevuta e portarla alla convocazione.", font=font(24), fill=(0, 0, 0))
    y += 70
    d.text((70, y), "Importi versati: bollettino e contributo (cifre omesse nel fac-simile)", font=font(22), fill=(70, 70, 70))
    d.text((W // 2, H - 60), "Documento inventato per la demo di Leggimi (Claude Impact Lab Milano, 3/10/2026).",
           font=font(20, True), fill=RED, anchor="mm")
    return photo_look(watermark(img), 1)


def avviso_comune() -> Image.Image:
    img, d = base_sheet("Avviso di esempio - non è un documento del Comune di Milano")
    y = 190
    d.text((70, y), "UFFICIO ANAGRAFE - AVVISO DI ESEMPIO (non ufficiale)", font=font(28, True), fill=(20, 20, 60))
    y += 60
    d.text((70, y), "Prot. n.", font=font(24), fill=(0, 0, 0))
    covered(d, 170, y - 2, 300, "PROTOCOLLO COPERTO")
    d.text((500, y), "del 22/09/2026", font=font(24), fill=(0, 0, 0))
    y += 70
    d.text((70, y), "Oggetto: comunicazione di avvio del procedimento -", font=font(28, True), fill=(0, 0, 0))
    y += 38
    d.text((70, y), "dichiarazione di residenza con provenienza dall'estero", font=font(28, True), fill=(0, 0, 0))
    y += 70
    lines = [
        "Gentile Sig. MAHMOUD ESEMPIO (nome inventato),",
        "",
        "la dichiarazione di residenza presentata online il 18/09/2026",
        "per l'indirizzo VIA DEGLI ESEMPI 0, MILANO (indirizzo inventato)",
        "è stata registrata.",
        "",
        "Gli effetti giuridici dell'iscrizione decorrono dalla data di",
        "presentazione della dichiarazione. L'ufficio effettuerà gli",
        "accertamenti previsti. Se gli accertamenti danno esito negativo,",
        "riceverà una comunicazione e potrà presentare memorie o documenti.",
        "",
        "Per informazioni sullo stato della pratica utilizzi la sezione",
        "\"Hai ancora bisogno di aiuto?\" del sito del Comune.",
        "",
        "Conservi questo avviso insieme al passaporto e alla ricevuta",
        "della richiesta di permesso di soggiorno.",
    ]
    for ln in lines:
        d.text((70, y), ln, font=font(27), fill=(0, 0, 0))
        y += 40
    y += 30
    d.text((70, y), "L'Ufficiale d'Anagrafe (firma omessa nel fac-simile)", font=font(22), fill=(70, 70, 70))
    d.text((W // 2, H - 60), "Documento inventato per la demo di Leggimi (Claude Impact Lab Milano, 3/10/2026).",
           font=font(20, True), fill=RED, anchor="mm")
    return photo_look(watermark(img), 2)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ricevuta_poste().save(OUT / "ricevuta_poste_facsimile.jpg", quality=86)
    avviso_comune().save(OUT / "avviso_comune_facsimile.jpg", quality=86)
    print("Scritti:", *sorted(p.name for p in OUT.glob("*.jpg")))


if __name__ == "__main__":
    main()
