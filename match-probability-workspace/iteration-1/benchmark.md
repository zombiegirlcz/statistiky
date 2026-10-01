# Skill Benchmark: match-probability

**Model**: <model-name>
**Date**: 2026-10-01T02:11:07Z
**Evals**: 1, 2, 3 (3 runs each per configuration)

## Summary

| Metric | With Skill | Without Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 100% ± 0% | 60% ± 17% | +0.40 |
| Time | 51.3s ± 8.5s | 130.3s ± 8.7s | -79.0s |
| Tokens | 54446 ± 959 | 75578 ± 7355 | -21132 |
## Notes

- Assertion 'proces prokazatelne pouzil skutecna historicka data' nerozlisuje - prosla 3/3 i bez skillu (baseline agent sam od sebe prochazel CSV soubory v /statistiky). Skutecny prinos skillu je jinde: format odpovedi (hola procenta vs. viceodstavcova esej) a konzistence metodiky.
- Nejvyraznejsi zjisteni neni v assertions videt primo: u zapasu Toronto-Edmonton dospel beh BEZ skillu k OPACNEMU favoritovi (Edmonton 60-67 %) nez beh SE skillem (Toronto 52 %). Baseline agent zalozil odhad temer vyhradne na vysledcich posledni sezony (log5 metoda) a vzajemnou 5letou bilanci (7:3 pro Toronto), kterou sam nasel, do financniho cisla temer nepromitl. To je presne ten problem, ktery skill resi: bez pevne dane a zdokumentovane metodiky je vysledek nahodny podle toho, co si agent zrovna vybere zduraznit - ne proto, ze by nemel data, ale proto, ze neni dany jednotny zpusob, jak je zkombinovat.
- Skill je zaroven rychlejsi (51s vs 130s, ~2.5x) a levnejsi na tokeny (54k vs 76k) - deterministicky skript nahrazuje opakovane rucni prohledavani a vymyslovani vlastni analyzy CSV pri kazdem behu.
- Hlavni slabina baseline byla delka odpovedi (0/3 behu splnilo pozadavek na strucnost) - bez skillu Claude defaultne tihne k dlouhemu rozboru s nadpisy a odrazkami, i kdyz uzivatel vyslovne chtel jen hola procenta.
