# Kura

**The anime companion for your media server.**

A media server streams your library to every screen. Kura gets the library right first. It
recognises every episode, film and OVA in your folders, shows you what's missing, files everything
the way popular media server apps expect, and brings every video up to one standard, with AI
upscaling for old SD episodes. Kura (蔵, "storehouse") runs on your Windows PC beside the server
you already use, and changes nothing until you say yes. It's for the videos you already have:
Kura never finds, downloads or shares anime.

[**Download for Windows**](https://frankgrobbelaar.github.io/kura/) · free and open source · no account

![Kura's home: what's in your library, and what needs you](docs/readme/home.png)

## Made for anime

Anime libraries are rarely tidy: long series numbered straight through where seasons are
expected, specials and OVAs in odd places, films that sit between series, file names in every
style, SD beside HD. Media server apps match files by their names and folders, so an untidy
library shows up with gaps, the wrong seasons and missing artwork. Kura puts the library itself in
order and tells you what's missing, so your media server finds every file where it should be.

## How it works

### 1. Point it at your folders

One anime per folder, a franchise in sub-folders, or everything in one heap: Kura reads every
video (length, picture, sound and subtitles) and finds each one on AniList and TMDB. Anything it
isn't sure of waits for you on "Which anime is this?", with stills and a quick look at the file.

![Which anime is this? Stills, what reading the file showed, and Kura's best guesses](docs/readme/match.png)

### 2. See what's missing

Every title gets a page: its seasons, an episode map, the episodes that aired that you don't have,
and a gap report beside the files. A franchise's page even shows the films and OVAs you have none
of, each in its place, and keeps watching for new ones.

![A franchise's page, the titles you're missing as dotted placeholders](docs/readme/franchise.png)

### 3. Tidy up

Kura files everything in the layout media server apps read, `TV\Show (Year)\Season 01\…` and
`Movies\Title (Year)\…`, with subtitles moving alongside. It proposes the changes title by title;
nothing moves until you apply them, and History undoes any of it.

![Tidy up: what Kura proposes, a title at a time](docs/readme/tidy.png)

### 4. Bring it all to one standard

Choose 1080p or 720p and Kura encodes HEVC 10-bit on your graphics card: SD gets an AI upscale,
720p gets Anime4K, and "See it first" shows a frame before and after. The queue can run at night,
waits when a drive is full, and checks every result before it replaces the original.

![The queue: the file converting now and what's next](docs/readme/queue.png)

### 5. Check it, right there

A small player is built in, for a quick look or a whole episode: it floats over the page wherever
you drag it, and goes full screen with the sound and subtitles the file has. Your media server
does the rest, on the TV, the phone or wherever you watch.

![The player full screen, sound and subtitles open](docs/readme/player-full.png)

## Alongside your media server

| | |
| --- | --- |
| **Same folders** | Kura works on the folders your media server already watches; its next scan sees the changes. |
| **Its layout** | Show and season folders and file names as media server apps read them: no release tags, resolutions or codecs. |
| **Its pictures** | Poster and background images beside each show, if you want them, for servers that use them. |
| **Hands off** | Kura never touches your media server, its database or its settings. |

## Safe by design

| | |
| --- | --- |
| **Asks first** | Renames, moves, deletions and conversions are proposed, then applied on your word. |
| **Undoes** | History puts back any tidy-up, and any converted file's original. |
| **Keeps copies** | What's replaced or deleted waits 30 days in quarantine on its own drive. |
| **Stays local** | No account and no cloud; nightly backups and a one-zip export. |

## Your own videos only

Kura looks after video files that are already on your PC, and plays them only in its own window.
It never searches for, downloads or shares anime or any other video, never streams it over the
internet, and doesn't get around copy protection. Use it only with videos you have the right to
keep and watch: Kura is not for piracy, in any form.

Kura contains no anime, artwork or other media. The titles in these pictures are made up, the
posters are Kura's own placeholders and the video playing is a stand-in; where Kura's code and
notes name a real series, it's only as example data. AniList and TMDB, where Kura looks titles
up, are their owners' trademarks, and Kura isn't affiliated with or endorsed by either, nor by
any media server app. This product uses the TMDB API but is not endorsed or certified by TMDB.

## Download

From the [downloads page](https://frankgrobbelaar.github.io/kura/): Windows 10 or 11, 64-bit,
every version with what changed. Kura updates itself. It isn't code-signed, so SmartScreen warns
the first time: More info › Run anyway. The installer's first page lists everything Kura
downloads, such as ffmpeg on the first run.

## Licence

Free software under the [MIT licence](LICENSE), with no warranty; what it's built on is listed,
each part with its licence, in `THIRD-PARTY-NOTICES.txt` with every release. Fork it freely; this
repository doesn't take contributions.
