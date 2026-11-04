
# from https://elinux.org/RPi_Text_to_Speech_(Speech_Synthesis)
AUDIO_DEVICE="${AUDIO_DEVICE:-plughw:CARD=UACDemoV10,DEV=0}"
espeak -ven+f2 -k5 -s150 --stdout "I can make the Pi say anything at all" | aplay -D "$AUDIO_DEVICE"
 
