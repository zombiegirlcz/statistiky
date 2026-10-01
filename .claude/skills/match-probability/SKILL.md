---
name: match-probability
description: Spočítá pravděpodobnost výsledku nadcházejícího fotbalového, tenisového nebo hokejového zápasu na základě kompletních historických dat uložených v /statistiky (5 sezón, stovky tisíc řádků - vzájemné zápasy, forma, rohy, esa, přesilovky atd.). Použij tento skill VŽDY, když se uživatel zeptá na šance, pravděpodobnost, tip, predikci nebo "kdo vyhraje" u konkrétního zápasu dvou týmů nebo hráčů ve fotbale, tenise či hokeji - stačí že zmíní dva soupeře proti sobě (např. "co myslíš, Sinner vs Alcaraz?", "jaké má šance City doma na Liverpool", "vyhraje Toronto nad Edmontonem?"), i když nepoužije slovo "pravděpodobnost". Nikdy neodhaduj výsledek jen z obecné znalosti nebo paměti - tento skill vynucuje, že se musí nejdřív sáhnout do reálných dat.
---

# Pravděpodobnost zápasu

## Proč tenhle skill existuje

Když se někdo zeptá "kdo vyhraje Arsenal - Chelsea", je lákavé odpovědět z obecné intuice ("Arsenal je silnější, dám jim 60 %"). To je ale jen hádání se škálou procent navrch - vypadá to přesvědčivě, ale není to podložené ničím skutečným. V `/statistiky` leží kompletní zápasová historie (5 sezón, desetitisíce zápasů se skóre, rohy, esy, přesilovkami...) přesně proto, aby se tohle hádání nemuselo dít. Úkol tady není "odhadni", ale "spočítej z dat, která máš k dispozici".

## Postup

### 1. Rozpoznej sport a dvojici

Z dotazu urči, jde-li o fotbal, tenis nebo hokej, a jména obou stran. Pokud je sport nejasný (např. jméno týmu existuje ve více sportech), zeptej se nebo to odvoď z kontextu (jméno hráče = skoro jistě tenis; dva kluby = fotbal nebo hokej podle názvu).

### 2. Spusť agregační skript - nespoléhej na ruční čtení

Soubory v `fotbal/` mají až tisíce řádků a `tenis/` desetitisíce - ruční prohledávání `grep`em je pomalé a náchylné k tomu, že něco přehlédneš (např. zápas ve staré sezóně, nebo zápas, kde je tým uvedený pod mírně jiným zápisem). Skript `scripts/aggregate_stats.py` projde VŠECHNY relevantní soubory pro daný sport, najde VŠECHNY zápasy obou stran i jejich vzájemné duely, a spočítá to spolehlivě:

```bash
python3 .claude/skills/match-probability/scripts/aggregate_stats.py fotbal "Arsenal" "Chelsea"
python3 .claude/skills/match-probability/scripts/aggregate_stats.py tenis "Sinner" "Alcaraz"
python3 .claude/skills/match-probability/scripts/aggregate_stats.py hokej "Toronto" "Edmonton"
```

Jména nemusí sedět na znak přesně (skript dělá fuzzy matching), ale musí být rozpoznatelná - u fotbalu/hokeje zkus nejdřív běžný název klubu (viz `references/nazvy_tymu.md` pro mapování na přesné názvy/zkratky v datech, hlavně u hokeje, kde se v CSV používají 3písmenné zkratky jako TOR, EDM).

Pokud víš, který tým hraje doma, přidej `--home A` nebo `--home B` (výchozí je, že doma hraje první zadaný tým - u fotbalu a hokeje to ovlivňuje výsledek, protože domácí výhoda je reálný a měřitelný efekt v datech).

**Pokud skript vypíše CHYBA** (nenašel tým/hráče jednoznačně), nehádej náhradní jméno sám - buď zkus jiný běžný tvar jména (zkratka, celé jméno klubu), nebo se zeptej uživatele, kterého přesně tým/hráče myslí.

### 3. Zkontroluj, že čísla dávají smysl

Skript na konci vypíše návrh procent, ale než je použiješ, projdi si i surová čísla nad ním - kolik zápasů bylo k dispozici (pokud jen pár, výsledek je méně spolehlivý), jak vypadá vzájemná bilance a nedávná forma. Pokud je najednou něco v nepoměru (např. tým s hroznou formou vychází silný favorit), zkontroluj, jestli skript nenašel špatný tým kvůli nejednoznačnému jménu.

Metodika výpočtu (váhy, proč zrovna takhle) je v `references/metodika.md` - přečti si ji, pokud se tě uživatel zeptá, PROČ vyšlo zrovna takové číslo, nebo pokud chceš váhy u konkrétního zápasu jemně upravit (např. když jeden hráč/tým má čerstvé zranění nebo jde o finále s jinou motivací - takové kontextové věci skript neumí vidět v číslech, ale ty o nich můžeš vědět).

### 4. Odpověz stručně

Uživatel chce HOLÁ PROCENTA, ne esej. Formát odpovědi:

- **Fotbal**: `Tým A XX % / Remíza YY % / Tým B ZZ %`
- **Tenis**: `Hráč A XX % / Hráč B YY %`
- **Hokej**: `Tým A XX % / Tým B YY %` (v NHL je vždy vítěz, díky prodloužení/nájezdům)

Žádné dlouhé zdůvodňování navíc. Pokud se uživatel zeptá "proč" nebo "na základě čeho", teprve pak rozveď klíčová čísla (formu, vzájemnou bilanci) ze skriptového výstupu.

## Když data chybí

Skript hledá jen v tom, co je v `/statistiky` - u fotbalu je to 22 evropských lig, u hokeje jen NHL, u tenisu prakticky celá ATP/WTA túra (viz `/statistiky/README.md` pro přesný rozsah). Pokud se někdo zeptá na zápas mimo tento rozsah (např. mimoevropský klub, KHL, MS v hokeji), skript žádná data nenajde - v tom případě to uživateli řekni rovnou, místo abys dopočítal procenta z ničeho. Je v pořádku říct "na tenhle zápas nemám v datech dost podkladů."
