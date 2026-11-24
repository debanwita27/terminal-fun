# Terminal animations to watch while Claude works

Small, fun ASCII animations to run in one terminal while Claude works in another. These are ideas, references and sources, grouped by category.

> **About the sources.** GitHub links come from search results. Only the donut-math page and awesome-terminal-art were opened directly. Pinterest showed boards, not individual pins. **Searching X/Twitter returned no post URLs**, so that section lists search terms to try by hand rather than made-up links.

---

## Try these now (no install)

```sh
curl parrot.live                 # party parrot
curl ascii.live/donut            # also: knot, nebulae, dvd, coin, nyan, parrot …
ssh movie.gabe565.com            # an ASCII movie over ssh
```

---

## 1. Vehicles & passers-by

| Idea | Existing ref | Notes for our version |
|---|---|---|
| Steam train (the original) | [sl](https://github.com/mtoyoda/sl) | — |
| Ships passing in an aquarium | [asciiquarium](https://github.com/cmatsuoka/asciiquarium) | — |
| Flying cat with a rainbow trail | [nyancat](https://github.com/klange/nyancat) | Use our own character, not Nyan |
| Space fly-by / starfield | [tspace](https://github.com/mtklr/tspace) | — |
| **New:** biplane pulling a banner | — | Banner text: random dev quip or Claude's current task |
| **New:** hot air balloon dropping sandbags | — | One sandbag per finished tool call? |
| **New:** rocket launch with countdown | — | Launches when Claude finishes |
| **New:** tiny city traffic, a pedestrian crossing | — | Endless, loops calmly |

## 2. Nature & ambient (calm, good to leave running)

| Idea | Existing ref |
|---|---|
| Aquarium | [asciiquarium](https://github.com/cmatsuoka/asciiquarium) |
| Growing bonsai | cbonsai (home reportedly gitlab.com/jallbrit/cbonsai, unverified) · Go port [gobonsai](https://github.com/nothub/gobonsai) |
| Lava lamp | [lavat](https://github.com/AngelJumbo/lavat) |
| Rain | [ascii-rain](https://github.com/nkleemann/ascii-rain) |
| Snowfall | [snowmachine](https://github.com/sontek/snowmachine) |
| Weather scenes | [weatherspect](https://robobunny.com/projects/weatherspect/html/) |
| Fire | [tfire](https://github.com/tech-chad/tfire) · [aalib / aafire](https://aa-project.sourceforge.net/aalib/) |
| **New:** day → night sky with a shooting star | — |
| **New:** pond with ripples and a jumping frog | ([duckpond.sh](https://github.com/gsobell/duckpond.sh) exists, not reviewed) |
| **New:** campfire whose sparks rise faster while Claude is busy | — |

## 3. Generative & math (hypnotic)

| Idea | Existing ref |
|---|---|
| Spinning 3D donut | [donut.c explainer (a1k0n)](https://www.a1k0n.net/2011/07/20/donut-math.html) |
| Pipes | [pipes.sh](https://github.com/pipeseroni/pipes.sh), plus siblings [pipesX](https://github.com/pipeseroni/pipesX.sh), [snakes](https://github.com/pipeseroni/snakes.pl), [weave](https://github.com/pipeseroni/weave.sh), [maze](https://github.com/pipeseroni/maze.py) |
| Matrix rain | [cmatrix](https://github.com/abishekvashok/cmatrix) · [unimatrix](https://github.com/will8211/unimatrix) |
| Fireworks, starfield, Life, Pollock | [gh-screensaver](https://github.com/vilmibm/gh-screensaver) |
| Metaballs, plasma, moiré | [cacademo (libcaca)](https://linux.die.net/man/1/cacademo) |
| Fractal zoom | [XaoS](https://github.com/xaos-project/XaoS) (`-driver aa -autopilot`) |
| Fire, galaxy, starry sky | [asciifx](https://github.com/4kanksh/asciifx) |
| Big pattern collections | [ascii-splash](https://github.com/reowens/ascii-splash) (17 patterns) · [ascii-magic-art](https://github.com/kailashsr38/ascii-magic-art) (`npx ascii-magic-art`) |
| **New:** falling sand / hourglass that flips when Claude finishes | — |
| **New:** boids flocking | — |

## 4. Characters & creatures (the "awww" category)

| Idea | Existing ref |
|---|---|
| Party parrot | [parrot.live](https://github.com/hugomd/parrot.live) · [terminal-parrot](https://github.com/jmhobbs/terminal-parrot) |
| Curl-able animation pack | [ascii.live](https://github.com/hugomd/ascii-live) |
| ASCII movie | [ascii-movie](https://github.com/gabe565/ascii-movie) |
| Talking cow | [cowsay (JS port)](https://github.com/piuccio/cowsay) |
| **New:** cat walks in, grooms itself, naps, and wakes when Claude is done | — |
| **New:** dancing robot with a new move every loop | — |
| **New:** a row of ducks crossing, with one always late | — |
| **New:** a slime that bounces and splits | — |

## 5. Gags & fake-busy

| Idea | Existing ref |
|---|---|
| Fake compile, download and crypto activity | [genact](https://github.com/svenstaro/genact) |
| "Sneakers"-style decrypt reveal | [no-more-secrets](https://github.com/bartobri/no-more-secrets) |
| Hacker split-screen | [hollywood](https://github.com/dustinkirkland/hollywood) |
| Bouncing DVD logo | [termdvd](https://github.com/nyankittone/termdvd) |
| Text reveal effects (burn, scatter, decrypt) | [TerminalTextEffects](https://github.com/ChrisBuilds/terminaltexteffects) |
| Screensaver packs | [termsaver](https://www.github.com/brunobraga/termsaver) · [ascsaver](https://gitlab.com/mezantrop/ascsaver) |
| **New:** progress bar that goes backwards ("99%… 98%…") | — |
| **New:** a slot machine that spins up dev excuses ("works on my machine") | — |
| **New:** coffee cup filling up, steam rising | — |

## 6. Lightly interactive

| Idea | Existing ref |
|---|---|
| Pannable world map | [mapscii](https://github.com/rastapasta/mapscii) |
| Clock / screensaver | [tty-clock](https://github.com/xorg62/tty-clock) |
| Audio visualizer | [cava](https://github.com/karlstav/cava) |
| **New:** press space to feed the fish or poke the cat | — |

## 7. Claude-aware (the different angle)

Others have started down this road:

- [claudelab](https://pypi.org/project/claudelab/): an isometric office with an ASCII mode, meant for a tmux pane beside Claude.
- [claude-office](https://www.ruby-toolbox.com/projects/claude-office): a kaomoji office that reads Claude transcripts.
- A feature request for an animated mascot in the status line, seen on a third-party mirror of the Claude Code issue tracker: [#35249](https://claudeissues.com/issue/35249-feature-custom-animated-character-mascot-display-in-the-status-line).
- A Reddit post about a bouncing-DVD overlay while Claude thinks, driven by hooks on macOS. It was found only through an archive mirror and is unverified.

**Our possible twist:**
1. Claude Code hooks (`PreToolUse`, `PostToolUse`, `Stop`) write a status file.
2. The animation reads it. The train speeds up while tools run, the balloon drops a sandbag per tool call, and a **fireworks finale plays on `Stop`**, so the animation also tells you Claude is done.
3. A `wait-fun` command picks a random animation each time, the way `sl` surprises you.

---

## Visual inspiration (Pinterest)

Pinterest returned boards only. These show the ANSI, BBS and PETSCII look, good for palettes and character style:

- [ASCII/ANSI art (maxneaves)](https://www.pinterest.com/maxneaves/asciiansi-art/): ANSI, PETSCII, text-mode demoscene
- [ANSI/ASCII art (Dioxolane)](https://www.pinterest.com/Dioxolane/ansiascii-art/): animated ASCII mixed with pixel-art GIFs
- [ANSI/ASCII-esque (lemasterdj)](https://www.pinterest.com/lemasterdj/ansiascii-esque/)
- [ANSI (quaseobjeto)](https://br.pinterest.com/quaseobjeto/ansi/): includes Blocktronics group pieces
- [ANSI art BBS](https://au.pinterest.com/customartistnetwork/ansi-art-bbs/): BBS-era style

## Twitter / X

No post URLs came back, because X content is mostly login-walled to search engines. Search these terms by hand while logged in:

- `ascii animation terminal`, `ascii shader`, `donut.c`, `#creativecoding ascii`, `#demoscene textmode`, `terminal screensaver`, `#ansiart`

## Other archives & galleries

- [16colo.rs](https://16colo.rs/): huge ANSI/ASCII art archive (idea: an "ANSI gallery slideshow" mode)
- [PhMajerus/ANSI-art](https://github.com/PhMajerus/ANSI-art)
- [Roy/SAC ANSI collection](http://www.roysac.com/roy_ansishow.html)
- [Tenor GIF for CLI (Google)](https://opensource.googleblog.com/2018/06/tenor-gif-for-cli.html): converts GIFs to ASCII
- Curated lists: [awesome-terminal-art](https://github.com/mcthomas/awesome-terminal-art) · [awesome-ascii-animation](https://github.com/mu-ct/awesome-ascii-animation) · [itsfoss roundup](https://itsfoss.com/ascii-art-linux-terminal/)

---

## Suggested first builds

1. **Fireworks on `Stop`.** It ties into hooks and is genuinely useful as a "done" signal.
2. **Biplane with a banner.** Quick to build and personalizable.
3. **Aquarium-style ambient scene.** Runs forever, with many small random events.
4. **The `wait-fun` random picker** that ties them all together.
