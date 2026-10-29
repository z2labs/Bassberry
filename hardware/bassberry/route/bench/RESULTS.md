# Router benchmark – Bassberry rev 0.2 (2026-10-29, 1. kör)

Közös bemenet: `bassberry_bench.dsn` = a placed, routolatlan tábla (158 net, ebből 117 routolandó, GND = In2 sík),
0,15 mm netclass clearance (a flow szabályai; a KiCad alap 0,2 mm-rel 13 töltő-QFN netnek nincs útja), `bench_rules.json`
(a flow pass3 szabályai minden netre). Minden eredményt ugyanarra a KiCad táblára importálunk és ugyanazzal a kicad-cli DRC-vel
mérünk (`_bench_eval.py`), így a minőségi számok hardverfüggetlenek.

## Minőség (hardverfüggetlen)

| router | gép | fal idő | G7-egyenérték* | kész net | nem kötött elem | via | huzal mm | routing DRC | iteráció |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| srouter feat/congestion-map, H/V irány, -it 60 -stall 10 | G7 (8 szál) | 112 s | ~130 s (1 szálra) | 111/117 | 20 | 532 | 4911 | 8 (furat-furat) | 21 |
| freerouting-rs 0.1 (enhanced profil, DSN) | rb-frs VM (1 szál) | 900 s | ~666 s | 115/117 | 2 | 413 | 5050 | 2 (lógó via) | 23 |
| freerouting-rs (kicad_pcb be/ki) | rb-frs VM | fut (>50 min) | – | – | – | – | – | – | – |
| PCBWorld (FreeRouting Java / KRT baseline) | rb-pcbworld VM | motor lefordult (nng 1.x kellett), futtatás a következő kör | | | | | | | |

\* gépindex = EGY azonos, egyszálú srouter iteráció ideje a bench bemeneten: G7 25,6 s · Z170 10,8 s · rb-frs VM 34,6 s
(E5649 Xeon, mellette futott az frs2). G7-egyenérték = fal idő / (index / index_G7). A srouter 8 szálon csak ~1,2×
gyorsabb az 1 szálnál (21 s vs 25,6 s az 1. iteráció), ezért ~130 s az egyszálú egyenértéke.

Tanulság: a freerouting-rs több netet fejez be (115 vs 111) és kevesebb viával, a srouter ~5× gyorsabb. A srouter 6
netje "conflict"-ben maradt (töltő QFN környéke: CHG_LX2, CHG_BST1/2, CHG_HG1_R/LG1_R, CHG_VIN) – ugyanott, ahol a
freerouting-rs is a két hiányzóját hagyta (CHG_LG2_R, CHG_HG2_R). A srouter a Q102 azonos netű lábait (ZVD_B) nem köti
össze egy alkatrészen belül – ez srouter-hiba, nem placement.

## GPU (Z170, GTX 1080, srouter feat/cuda-wavefront)

Paritás (check mód, bench DSN, 2 iteráció, 442 kapcsolat, minden kapcsolat CPU-n ÉS GPU-n):
same optimum 175, GPU jobb 267 (2–5 % olcsóbb út: a GPU egzakt címkejavító keresés, a CPU A* heurisztika-súllyal),
GPU rosszabb 0, "nincs út" eltérés 0 → **paritás 100 %**.

Sebesség ugyanazon a gépen (CPU A* vs GPU hullámfront, kapcsolatonként):

| CPU A* kiterjesztés | db | CPU ms | GPU ms | gyorsulás (medián) | max |
|---|---:|---:|---:|---:|---:|
| < 10 k | 130 | 1,0 | 12,7 | 0,07× | 0,6× |
| 10–50 k | 120 | 6,3 | 19,5 | 0,30× | 1,0× |
| 50–200 k | 81 | 27,9 | 31,5 | 0,93× | 2,1× |
| 200 k–1 M | 98 | 118 | 133 | 1,17× | 3,9× |
| > 1 M | 13 | 351 | 281 | 1,41× | 2,5× |

Teljes pass1b futás (flow szabályok, 57 power net): CPU 4 szál **78 s/iteráció**, 30 iteráció 2302 s, 53/57 net,
4958 M kiterjesztés; GPU minden ≥1,5 M csomópontos ablakra: **232 s/iteráció**; GPU csak a fallback (korridor nélküli /
egész táblás) keresésekre: **225 s/iteráció** → a GPU ezen a táblán 3× lassabb, leállítva.

Miért: a Bassberry ablakai 0,5–14 M csomópontosak, de a CPU A* célirányosan 1–100 k kiterjesztéssel végez; a GPU
hullámfront kötött költsége (allokáció + feltöltés + ezres sweep-számú kernelindítás) 10–30 ms, és "nincs út" esetben az
egész elérhető tartományt bejárja. OrthoRoute-nál a GPU azért nyer, mert egyetlen óriás rács egyszerre számol ezer netre.
A pass1b 77 s-os, net-számtól független iterációideje 3 kiúthatatlan net egész táblás újrakeresése (~25 s/db, ~55 M
kiterjesztés) MINDEN iterációban – ezt nem GPU-val, hanem egyszeri elérhetőség-teszttel kell kiölni (következő lépés).

## Következő lépések
1. srouter: statikus elérhetőség-teszt a terminálokra (csak fix akadályokkal), egyszer – a "no path" net ne keressen újra
   egész táblán minden iterációban (pass1b 2302 s → becsült ~3 min).
2. srouter: azonos netű lábak egy alkatrészen belül (Q102 ZVD_B) összekötése.
3. GPU: csak akkor érdemes, ha egy kereséshez előre becsülten >200 k kiterjesztés kell; perzisztens bufferek + bucketed
   (delta-stepping) frontier csökkentené a fix költséget – mérés után döntünk, egyelőre opcionális feature marad.
4. PCBWorld baseline-ok (FreeRouting Java, KRT) a bench táblán + freerouting-rs kicad_pcb mód eredménye.
