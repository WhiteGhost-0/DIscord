# Boba Commands List

## Chat and Memory
@BOBA [message] - Chat with Boba
@BOBA tag @user - Forces Boba to mention the user
@BOBA mention me when @user replies - Boba will ping you the next time they speak
!remember [fact] - Save a fact about yourself
!remember @user [fact] - Save a fact about someone else
!memories - View facts Boba knows about you
!memories @user - View facts Boba knows about another user
!forget - Clear all your personal memories
!clear - Clear short-term conversation memory for the channel

## Music (Must be in Voice Channel)
!play [song name or URL] - Search and play a song, or add to queue
!skip - Skip current song
!pause - Pause playback
!resume - Resume playback
!stop - Stop music and clear the queue
!queue - View upcoming songs
!now - View currently playing song
!loop - Toggle loop for current song
!volume [1-100] - Adjust music volume
!join - Make Boba join your current voice channel
!disconnect - Make Boba leave the voice channel

## Leveling
!level - View your level and XP
!level @user - View someone else's level and XP
!leaderboard - View the top 10 users by XP

## Moderation (Requires Admin/Mod Permissions)
!kick @user [reason] - Kick a user
!ban @user [reason] - Ban a user
!unban [username] - Unban a user by username
!mute @user [minutes] [reason] - Timeout a user
!unmute @user - Remove a timeout
!warn @user [reason] - Issue a warning (3 warnings = auto-kick)
!warnings @user - Check someone's warning count
!purge [number] - Delete the last X messages (max 100)
!addword [word] - Add a word to the auto-delete filter
!removeword [word] - Remove a word from the filter

## Setup and Utility (Requires Admin Permissions)
!setchannel welcome #channel - Set channel for welcome messages
!setchannel goodbye #channel - Set channel for leave messages
!setchannel announce #channel - Set channel for level-up announcements
!setchannel log #channel - Set channel for voice activity logs
!setautorole @role - Set a role to automatically give to new members
!announce #channel [message] - Send a formatted announcement to a channel
!poll "Question" "Option 1" "Option 2" - Create a reaction poll (up to 9 options)
!userinfo @user - View user account details
!serverinfo - View server details
!ping - Check bot latency
