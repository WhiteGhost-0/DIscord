# 🧋 Boba Command Cheat Sheet

Boba is an AI-powered Discord companion. She can chat natively, play music, moderate your server, and track XP! Here is everything she can do.

---

## 💬 Chatting & Interactions
Boba talks like a real person, remembers facts about you, and reacts to your messages.

* **Chatting:** Just `@BOBA` or reply to one of her messages! 
* **Auto-reactions:** She automatically reacts to words like `gm`, `gn`, `boba`, `love`, `lol`, etc.
* **Tag someone:** `@BOBA tag @user` (Forces a real ping)
* **Watch for replies:** `@BOBA mention me when @user replies` (She will ping you the next time they speak!)

---

## 🧠 AI Memory
Boba has persistent memory. You can tell her to remember facts about you or your friends.

* `!remember [fact]` — Tell Boba a fact about yourself (e.g. `!remember I love coffee`).
* `!remember @user [fact]` — Tell Boba a fact about someone else.
* `!memories` — See everything Boba remembers about you.
* `!memories @user` — See what Boba knows about another user.
* `!forget` — Wipes all of your personal memories from Boba's brain.
* `!clear` — Wipes Boba's short-term conversation memory for the current channel.

---

## 🎵 Music Commands
Boba can stream audio directly from YouTube! *(You must be in a Voice Channel to use these).*

* `!play [song name or URL]` — Searches for a song and plays it (or adds it to the queue).
* `!skip` — Skips the current song.
* `!pause` — Pauses the music.
* `!resume` — Resumes the music.
* `!stop` — Stops the music and clears the queue completely.
* `!queue` — Shows the upcoming list of songs.
* `!now` — Shows what is currently playing.
* `!loop` — Toggles loop mode for the current song.
* `!volume [1-100]` — Changes the music volume.
* `!join` — Forces Boba to join your current voice channel.
* `!disconnect` — Makes Boba leave the voice channel.

---

## ⭐ XP & Leveling
You automatically earn 15 XP every 60 seconds you chat (commands don't count!).

* `!level` — See your current level and XP.
* `!level @user` — See someone else's level.
* `!leaderboard` — Displays the Top 10 users with the most XP in the server.

---

## 🛡️ Moderation (Requires Permissions)
* `!kick @user [reason]` — Kicks a user from the server.
* `!ban @user [reason]` — Bans a user.
* `!unban [username]` — Unbans a user by their exact username.
* `!mute @user [minutes] [reason]` — Times out a user so they can't chat/speak.
* `!unmute @user` — Removes a timeout.
* `!warn @user [reason]` — Issues a warning. **3 warnings = Auto-Kick.**
* `!warnings @user` — Check how many warnings someone has.
* `!purge [number]` — Deletes the last X messages in the channel (max 100).
* `!addword [word]` — Adds a word to the auto-delete filter (Boba will delete messages with this word).
* `!removeword [word]` — Removes a word from the filter.

---

## ⚙️ Server Setup (Admin Only)
* `!setchannel welcome #channel` — Boba will welcome new users here.
* `!setchannel goodbye #channel` — Boba will announce when users leave here.
* `!setchannel announce #channel` — Level up notifications will be posted here.
* `!setchannel log #channel` — Boba will log who joins/leaves/moves in Voice Channels here.
* `!setautorole @role` — Boba will automatically give this role to anyone who joins.
* `!announce #channel [message]` — Sends a styled announcement embed to a channel.

---

## 🛠️ Utility
* `!poll "Question" "Option 1" "Option 2"` — Creates a reaction poll (up to 9 options).
* `!userinfo @user` — Shows account details, join date, and roles for a user.
* `!serverinfo` — Shows member count, creation date, and server details.
* `!ping` — Checks Boba's current latency/response time.
