"""
deploy/modal_app.py - automatizace tenisoveho sazkoveho agenta na Modalu.

ARCHITEKTURA (precti pred spustenim)
-------------------------------------
Rozhodl jsem se pro "scheduled tick" misto "always-on" serveru - diky tomu,
ze user na otazku neodpovedel, jde o muj navrh, ne jeho potvrzeny vyber;
zduvodneni a jak prepnout na druhou varintu je dole pod "ALWAYS-ON VARIANTA".

Duvody:
  1. CENA. Modal uctuje za kazdou sekundu bezici kontejneru. Agent, co
     "jen cekas a sleduje", by stal nepretrzite, i kdyz se zrovna nic
     nedeje (vetsinu dne nikdo nehraje zapas, na ktery by se dalo sazet).
  2. Sandbox ma TVRDY STROP 24 HODIN (viz modal.Sandbox.create: timeout
     max). Jeden vecne bezici kontejner neni ani technicky moznost -
     musel by se stejne kazdych ~24 h restartovat pres supervizor.
  3. Uz existujici architektura (cron_tick.sh na telefonu,
     live_tennis_simulator.py watch/status) je uz navrzena jako
     OPAKOVANY TIK, ne nepretrzity proces - tenhle skript jen presouva
     stejny rytmus z telefonu na Modal.

Misto toho: naplanovana Modal funkce (modal.Cron) se kazdych N minut
probudi, vytvori KRATKODOBY Sandbox (par minut zivota), v nem spusti
`pi` (pi-coding-agent) s jednim ukolem - zkontrolovat vysledky, pripadne
upravit strategii, spustit watch+vyhodnot - a Sandbox se pak sam ukonci.
Zadny vecne bezici kontejner, zadny 24h strop, plati se jen za ty minuty
behu.

CO JE NA MODAL VOLUME A PROC
-----------------------------
live_bets_log.jsonl (fiktivni banka a tikety) uz je SLEDOVANY V GITU (viz
.gitignore - neni tam vyjmuty) - git uz je zdroj pravdy sdileny mezi
telefonem a touhle Modal automatizaci. Repo proto NENI zapecene v image
(jako v OpenCode priklade z Modal dokumentace), ale lezi na perzistentnim
modal.Volume jako normalni git working tree: kazdy tik udela `git pull`,
pripadne zmeny na konci `git push`. Diky tomu vidi stejny stav telefon
i Modal, at zrovna bezel kdokoliv z nich.

SECRETS, KTERE SI MUSIS PRIPRAVIT PRED `modal deploy`
-------------------------------------------------------
  modal secret create tenis-sazkove-klice \
      SX_API_KEY=... SX_PRIVATE_KEY=... \
      LIVE_TENNIS_API_KEY=... ODDS_API_KEY=... \
      BOOKMAKER=sxbet_sim
      (presne stejne nazvy promennych, jake uz pouzivaji bookmaker.py/
       sxbet_client.py/live_tennis_simulator.py pres os.environ - zadna
       zmena kodu v scripts/ neni potreba.)

BEZPECNOSTNI POJISTKA (schvalne tvrda, ne jen doporuceni)
-----------------------------------------------------------
Pokud by nekdy BOOKMAKER v Secretu byl "sxbet_real" (realne sazeni),
tenhle skript navic vyzaduje ESTE JEDEN samostatny secret
"tenis-povoleni-realnych-sazek" s klicem CONFIRM=yes - bez nej run_tick()
odmitne sandbox vubec vytvorit. Dve nezavisle veci, co musi souhlasit,
misto jedne promenne, kterou by slo omylem prepnout.

JAK TO VYZKOUSET RUCNE (bez cekani na cron)
---------------------------------------------
    modal run deploy/modal_app.py

OVERENO LOKALNE (pi 0.87.1, mimo Modal sandbox, ale stejny binarni CLI)
--------------------------------------------------------------------------
`pi -p "..."` skutecne spusti neinteraktivni jednorazovy beh presne jak
tick.sh predpokladal. PUVODNI ODHAD `--allow-tool bash` ale byl SPATNE -
pi tenhle flag nezna. Spravny flag pro povoleni nastroju je `--tools`
(zkratka `-t`), napr. `--tools bash`. Overeno i funkcne: beh s `--tools bash`
sam spustil `bet_evaluator.py report` a spravne shrnul vystup. tick.sh uz
je na tenhle opraveny flag aktualizovany.

Config pro pi uz NENI z `docs_config_memo` repa (tim padem odpadl i
GH_TOKEN_SECRET, nikde jinde v tomhle souboru se nepouzival) - pouziva se
primo lokalni `/root/.arvhive/.pi`. add_local_dir ho zapece do image
stejne jako ostatni lokalni soubory.

POZOR - test skutecneho dotazu (ne jen `pi auth check`) ukazal, ze tenhle
konkretni adresar ma `auth.json` s klici pro anthropic i deepseek, ktere
SE AUTENTIZUJI (status "ready"), ale oba vraci "insufficient balance" na
realnem requestu - tedy maji klice, ne kredit. Ostatni providery v tom
auth.json (kilocode, openrouter, github-copilot, qwen-token-plan) se u
tyhle instalace v katalogu modelu vubec neobjevily (`pi --list-models`),
takze nejsou funkcne pouzitelne bez dalsiho doreseni. Nez na tomhle image
poustet produkcni tick, over `pi auth check` pro providera, co ma tick.sh
skutecne pouzivat, a pripadne dopln kredit/opravit klic - "ready" u auth
check neznamena "ma kredit".
"""
import modal

APP_NAME = "tenis-sazkovy-agent"
GITHUB_REPO = "zombiegilrcz/statistiky"
NVM_VERSION = "v0.40.1"

ENV_SECRET = "tenis-sazkove-klice"
REAL_BETTING_CONFIRM_SECRET = "tenis-povoleni-realnych-sazek"

VOLUME_NAME = "tenis-sazky-state"
VOLUME_MOUNT = "/data"

TICK_TIMEOUT_S = 15 * 60       # jeden tik smi bezet max 15 minut
TICK_SCHEDULE = "*/15 * * * *"  # kazdych 15 minut - uprav podle potreby


app = modal.App(APP_NAME)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _build_image() -> modal.Image:
    """Prevadi presne tvuj seznam prikazu do Modal Image build kroku."""
    image = (
        modal.Image.debian_slim()
        .apt_install("git", "curl", "ca-certificates")
        # "add local file ~/.gitconfig:~/" - commit identita pro `pi`, kdyz
        # bude pushovat zmeny strategie. copy=True, aby to videly i dalsi
        # build kroky (ne jen runtime).
        .add_local_file("/root/.gitconfig", "/root/.gitconfig", copy=True)
        # /root/.arvhive/.pi je lokalni pi-coding-agent config SE ZNAMA
        # FUNKCNI auth.json (anthropic + deepseek, overeno `pi auth check`) -
        # nejsou to klasicke env-var klice, takze nejdou do Modal Secretu,
        # kopiruji se proto rovnou do image. copy=True, aby je videly i
        # dalsi build kroky (instalace pi nize).
        .add_local_dir("/root/.arvhive/.pi", "/root/.pi", copy=True)
        # curl nvm, nvm install node, npm i -g pi-coding-agent - vsechno v
        # JEDNE bash -lc vrstve (nvm.sh se musi sourcnout ve stejnem shellu,
        # ktery pak volá `nvm`/`npm`), a na konci symlink do /usr/local/bin,
        # aby `pi`/`node`/`npm` fungovaly v KAZDEM dalsim prikazu/sandboxu
        # bez nutnosti znovu sourcovat nvm.sh.
        .run_commands(
            "bash -lc '"
            f"curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/{NVM_VERSION}/install.sh | bash && "
            "export NVM_DIR=\"$HOME/.nvm\" && "
            ". \"$NVM_DIR/nvm.sh\" && "
            "nvm install node && "
            "npm i -g @earendil-works/pi-coding-agent && "
            "NODE_BIN=$(dirname $(nvm which node)) && "
            "ln -sf $NODE_BIN/node /usr/local/bin/node && "
            "ln -sf $NODE_BIN/npm /usr/local/bin/npm && "
            "ln -sf $NODE_BIN/npx /usr/local/bin/npx && "
            "ln -sf $NODE_BIN/pi /usr/local/bin/pi"
            "'"
        )
        .add_local_file("tick.sh", "/root/tick.sh", copy=True)
        .run_commands("chmod +x /root/tick.sh")
    )
    return image


def _assert_safe_to_run(env_secret: modal.Secret) -> list[modal.Secret]:
    """Bezpecnostni pojistka: real sazeni vyzaduje DRUHY, nezavisly secret.

    Modal Secret obsah nejde precist z Python kodu pred tim, nez je
    pripojeny ke kontejneru (API to schvalne neumoznuje), takze kontrola
    "je BOOKMAKER=sxbet_real?" se musi delat AZ UVNITR sandboxu/tick.sh -
    tahle funkce jen rozhodne, JAKE secrets sandbox vubec dostane.
    """
    secrets = [env_secret]
    try:
        secrets.append(modal.Secret.from_name(REAL_BETTING_CONFIRM_SECRET))
    except modal.exception.NotFoundError:
        pass  # v poradku - demo rezim to nepotrebuje
    return secrets


def _run_tick():
    image = _build_image()
    env_secret = modal.Secret.from_name(ENV_SECRET)
    secrets = _assert_safe_to_run(env_secret)

    print("[modal_app] vytvarim tik-sandbox...")
    sb = modal.Sandbox.create(
        "bash", "-lc",
        (
            # Pojistka DRUHE urovne, tentokrat uvnitr kontejneru, kde uz
            # jde precist skutecny obsah secrets: real sazeni bez obou
            # potvrzeni (BOOKMAKER i CONFIRM) se tu natvrdo zastavi.
            'if [ "${BOOKMAKER:-sxbet_sim}" = "sxbet_real" ] && '
            '[ "${CONFIRM:-}" != "yes" ]; then '
            'echo "ZASTAVENO: BOOKMAKER=sxbet_real bez tenis-povoleni-realnych-sazek secretu"; '
            'exit 1; fi; '
            'exec /root/tick.sh'
        ),
        app=app,
        image=image,
        secrets=secrets,
        volumes={VOLUME_MOUNT: volume},
        timeout=TICK_TIMEOUT_S,
        workdir="/root",
    )
    for line in sb.stdout():
        print(line, end="")
    for line in sb.stderr():
        print(line, end="")
    exit_code = sb.wait()
    print(f"[modal_app] tik dokoncen, exit code {exit_code}")
    return exit_code


@app.function(schedule=modal.Cron(TICK_SCHEDULE), timeout=TICK_TIMEOUT_S + 60)
def scheduled_tick():
    """Produkcni vstup - Modal tohle vola sam podle TICK_SCHEDULE."""
    _run_tick()


@app.local_entrypoint()
def main():
    """Rucni test jednoho tiku: `modal run deploy/modal_app.py`."""
    _run_tick()


# ---------------------------------------------------------------------------
# ALWAYS-ON VARIANTA (zatim NEPOUZITA - jen poznamka, kdyby ses rozhodl jinak)
# ---------------------------------------------------------------------------
# Misto @app.function(schedule=...) by sel vytvorit JEDEN dlouho zijici
# Sandbox (timeout az do 24h) s `pi` spustenym jako server/smycka uvnitr,
# a samostatnou naplanovanou funkci "supervizor", co kazdych par hodin
# zkontroluje, jestli sandbox jeste zije (sb.poll()) a kdyz ne (nebo kdyz
# se blizi 24h strop), vytvori novy. Je to draz: plati se za KAZDOU
# sekundu, i kdyz se zrovna nic nedeje. Napis, pokud tohle chces misto
# scheduled ticku - je to jina struktura souboru, ne jen zmena parametru.
