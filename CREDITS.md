# Credits

terminal-fun's own code is MIT licensed (see [LICENSE](LICENSE)). Many pieces build on other people's work. Each piece's `META` dict says how, and this file collects those notes.

- **original**: our own idea and art.
- **inspired by**: the look or idea comes from the linked work. The code and art here were written from scratch; nothing from the original is copied.
- **taken from**: a specific form, algorithm, text or asset comes from the linked work, as described in the row.

If you made something listed here and want the credit changed or the piece removed, please open an issue.

## Third-party assets

No third-party image, sound or font files are committed to this repository.

- **bullethell** draws Srijan Paul's sprites and plays his sounds from [bullet_hell](https://github.com/srijan-paul/bullet_hell) (MIT, Copyright (c) 2020 Srijan Paul). It reads them from a sibling `bullet_hell/` clone or `$CLAUDE_FUN_BULLETHELL_ASSETS` if you have one. Otherwise it downloads them once from GitHub into `~/.cache/claude-fun/`. Until they arrive, or if you're offline, it draws its own stand-ins.
- **bonkyon** plays the sounds from [Bonkyon](https://github.com/srijan-paul/Bonkyon) (MIT, Copyright (c) 2020 inJuly). It downloads them once into `~/.cache/claude-fun/sounds/bonkyon/` on first run with sound, and falls back to synthesized stand-ins.
- Some of those sound files are from freesound.org, under the licences named in the table: CC BY 4.0 ([licence](https://creativecommons.org/licenses/by/4.0/)) or CC0. They are used as published, except that on macOS bonkyon's music is transcoded to AAC in your local cache.
- Every other sound is synthesized at runtime by `fun/synth.py`.
- `gallery.html` contains text-mode stills rendered from the pieces, including bullethell's sprites drawn as terminal cells. Those sprites are MIT licensed, with the notice above.

## Notes on "taken from" rows

- **swirl, original form**: a port of the two-line p5.js sketch that @yuruyurau posted publicly on X. The post states no licence. It is credited here and in the piece, and it will be removed if the author asks.
- **forest**: the branching is ported from H_TreeFractal (the author's own repo) and Frank's Laboratory's public CodePen. Public CodePens are MIT licensed under CodePen's terms.
- **typewriter**: *Ozymandias* (1818) is in the public domain. The other verse in the piece is original.

## By piece

Generated with `./wait-fun credits --markdown`.

| Piece | Credit | Who | Link |
|---|---|---|---|
| biplane | inspired by | sl by Toyoda Masashi | https://github.com/mtoyoda/sl |
| blackhole | inspired by | Raunak (@Skirook) | https://x.com/Skirook/status/2118944082093588748 |
| campfire | inspired by | Lode Vandevenne's fire effect tutorial | https://lodev.org/cgtutor/fire.html |
| catnap | original | - | - |
| celestial | inspired by | the classic ASCII Saturn (artist unknown) | https://ascii.co.uk/art/saturn |
| celestial | inspired by | a text-poem moon reflected in water (artist unknown) | - |
| codefire | inspired by | Andreas Gysin (@andreasgysin), Code is fire | https://x.com/andreasgysin/status/2015832561839206872 |
| daisy | inspired by | ASCII animation (artist unknown), via Pinterest user mofri_ann | https://in.pinterest.com/pin/1145462486504468167/ |
| daisy | inspired by | infoitsmostudio, Blooming poster | https://www.instagram.com/p/DZzbKsrCL6V/ |
| daisy | inspired by | flower mosaic (artist unknown), via Pinterest user kieradxn | https://in.pinterest.com/pin/125467539611670186/ |
| dyna | inspired by | Andreas Gysin (@andreasgysin), Dyna | https://x.com/andreasgysin/status/1957692884292968520 |
| dyna | inspired by | Paul Haeberli, DynaDraw (1989) | https://www.graficaobscura.com/dyna/ |
| excuses | original | - | - |
| fireworks | original | - | - |
| forest | taken from | H_TreeFractal by debanwita27 | https://github.com/debanwita27/Canvas_Stuff/tree/main/H_TreeFractal |
| forest | taken from | Frank's Laboratory, Random Fractal Tree Generator | https://codepen.io/franksLaboratory/pen/ZEbGoPB |
| forest | inspired by | drawille by asciimoo (braille-dot terminal drawing) | https://github.com/asciimoo/drawille |
| hourglass | inspired by | falling-sand games | https://en.wikipedia.org/wiki/Falling-sand_game |
| ink | inspired by | fluid ink animation (artist unknown), via Pinterest user asa01200 | https://in.pinterest.com/pin/757519599867416526/ |
| jellyfish | inspired by | Marcelo Design X (@MarceloDesignX) | https://x.com/MarceloDesignX/status/2114611049702011197 |
| koi | inspired by | sucodee (@sucodeee) | https://x.com/sucodeee/status/2113944922055410008 |
| meltdown | inspired by | Andreas Gysin (@andreasgysin), Meltdown | https://x.com/andreasgysin/status/2025601644826628115 |
| moire | inspired by | Andreas Gysin (@andreasgysin), Moiré Explorer | https://x.com/andreasgysin/status/2007755844981813567 |
| moire | inspired by | Sonya Rapoport (via Gysin's Moiré Explorer) | https://x.com/andreasgysin/status/2007755844981813567 |
| reef | inspired by | asciiquarium by Kirk Baucom | https://robobunny.com/projects/asciiquarium/html/ |
| reef | inspired by | Craig Reynolds, Boids (flocking) | https://www.red3d.com/cwr/boids/ |
| reef | inspired by | Steven Worley, A Cellular Texture Basis Function (caustics) | https://dl.acm.org/doi/10.1145/237170.237267 |
| sandpile | inspired by | Bak, Tang & Wiesenfeld, Abelian sandpile model (1987) | https://doi.org/10.1103/PhysRevLett.59.381 |
| sharks | inspired by | stacked (@stackedlol) | https://x.com/stackedlol/status/2112257760628986188 |
| skyline | original | - | - |
| spacecol | inspired by | Runions, Lane & Prusinkiewicz, Modeling Trees with a Space Colonization Algorithm (2007) | https://www.algorithmicbotany.org/papers/colonization.egwnp2007.html |
| spacecol | inspired by | drawille by asciimoo (braille-dot terminal drawing) | https://github.com/asciimoo/drawille |
| swirl | taken from | yuruyurau (@yuruyurau), the original form | https://x.com/yuruyurau/status/2080977918914969636 |
| swirl | inspired by | Wil.D (@crabhive), Mathematical Art Generator: medusa, ammonite, torus knot, tesseract | https://x.com/crabhive/status/2081064705905369429 |
| swirl | inspired by | Justin Lister (@justin_lister), Pulsating breathing | https://x.com/justin_lister/status/2081705225182953560 |
| tixy | inspired by | Martin Kleppe (@aemkei), tixy.land | https://tixy.land |
| tixy | inspired by | Martin Kleppe (@aemkei), 187 bytes ASCII Meta Balls | https://aem1k.com/meta/ |
| bonkyon | inspired by | Bonkyon by Srijan Paul (injuly) | https://injuly.itch.io/bonkyon |
| bonkyon | taken from | Bonkyon sound assets via Srijan Paul (injuly), MIT | https://github.com/srijan-paul/Bonkyon |
| bonkyon | taken from | 8bit blix (aka Lost Moons) by Questiion / Micah Young, CC BY 4.0, converted to AAC | https://freesound.org/people/Questiion/sounds/166392/ |
| bonkyon | taken from | 8-bit Game Over by Euphrosyyn, CC BY 4.0 | https://freesound.org/people/Euphrosyyn/sounds/442127/ |
| bonkyon | taken from | button-04 by JarredGibb, CC0 | https://freesound.org/people/JarredGibb/sounds/219477/ |
| bonkyon | taken from | positive-beeps by themusicalnomad, CC0 | https://freesound.org/people/themusicalnomad/sounds/253887/ |
| bonkyon | taken from | swosh-01 by qubodup, CC0 | https://freesound.org/people/qubodup/sounds/59988/ |
| bonkyon | taken from | Swosh 42 by qubodup, CC0 | https://freesound.org/people/qubodup/sounds/60029/ |
| bugsquash | original | - | - |
| bullethell | inspired by | bullet_hell by Srijan Paul (injuly) | https://github.com/srijan-paul/bullet_hell |
| bullethell | taken from | bullet_hell pixel art (player, fly, stinger, corpses, ball bullet, door, barrel, explosion, cursor, handgun, tilesheet) by Srijan Paul (injuly), MIT | https://github.com/srijan-paul/bullet_hell/tree/master/assets/image |
| bullethell | taken from | bullet_hell sound assets (hurt, hit, explosion, laser, spaceship music) via Srijan Paul (injuly), MIT | https://github.com/srijan-paul/bullet_hell/tree/master/assets/sound |
| bullethell | taken from | SFX Laser Shoot 02 by bolkmar, CC BY 4.0 | https://freesound.org/people/bolkmar/sounds/421704/ |
| bullethell | taken from | Attack.ogg by MortisBlack, CC BY 4.0 | https://freesound.org/people/MortisBlack/sounds/385049/ |
| bullethell | taken from | Retro video game sfx - Explode by OwlStorm (Ashe Kirk), CC0 | https://freesound.org/people/OwlStorm/sounds/404754/ |
| catstack | original | - | - |
| ducklings | original | - | - |
| forage | inspired by | Minesweeper by Robert Donner & Curt Johnson | https://en.wikipedia.org/wiki/Minesweeper_(video_game) |
| forage | inspired by | Simon Tatham's Mines (no-guess board generation) | https://www.chiark.greenend.org.uk/~sgtatham/puzzles/ |
| froghop | inspired by | Joan Stark (jgs) ASCII frogs | https://www.asciiart.eu/animals/frogs |
| typewriter | inspired by | Typewriter FX Photo Filter by Brian Krause (Adducive) | https://adducive.com/typewriter_fx |
| typewriter | inspired by | adducive, "Typewriter art of an Olympia typewriter. Made with Typewriter FX" (Pinterest) | https://in.pinterest.com/pin/792000284516165645/ |
| typewriter | inspired by | Flora Stacey, the typewritten butterfly (Pitman's Phonetic Journal, 1898) | https://oztypewriter.blogspot.com/2020/02/flora-fanny-stacey-1845-1909-worlds.html |
| typewriter | inspired by | Paul Smith (1921-2007), typewriter artist | https://en.wikipedia.org/wiki/Paul_Smith_(artist) |
| typewriter | verse taken from | Percy Bysshe Shelley, "Ozymandias" (1818) | https://en.wikipedia.org/wiki/Ozymandias |
