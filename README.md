# m3u to Podcast

More than once, I've hit the problem of not getting a good recording of my live broadcast
when I'm doing my radio show, which means no podcast for that week. 

I _do_ however, have the Music.app playlists that I use to play the music and
voiceover breaks, and I decided to assemble a handy little script to recreate
the _music_ portion of the podcast, allowing me to pull it into whatever editor
and record replacement voiceovers, giving me a slightly ersatz version of the
original.

Since a slightly fake live show is better than no show at all, I'm using this
to cover for me on those days when I screw the pooch and lose the recording.

## Usage

 1. Open Music.app and click on a playlist in the left sidebar.
 2. File > Library > Export Playlist...
 3. Select the target folder, and choose `m3u` as the output format..
 4. `python3 builder.py "Path to the.m3u"`

This will create a .txt file that has markers for each song and the time at which it played,
suitable for using the GitHub MP3 chapterizer, and an mp3 file of all the tracks in the playlist.

You will, of course have to adjust the cue points once you record voiceovers, but I plan to use
Davinci Resolve, which will make finding the new cue points at least a little easier.
