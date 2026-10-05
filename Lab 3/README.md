# Chatterboxes

Shifeng Hong (sh2769)
Arnav Whig (aw966)

# Part 1

## A. Text to Speech

> The neural TTS captures the "!", wth a upswinging tone, while the classic greet names with plain tone.

## B. Speech to Text

<img width="952" height="788" alt="image" src="https://github.com/user-attachments/assets/fb63feb0-6398-4f08-b8c9-dc403d6fc9b3" />
> **base.en** balance between delay and accuracy. For a system that has to answer you, missing a comma wouldn't be issue.

[ask_number](speech-scripts/ask_number.sh)
## C. Turn-taking: knowing when someone has stopped talking

<img width="1040" height="622" alt="image" src="https://github.com/user-attachments/assets/465bc0e7-1d4e-4715-a273-223c9485a002" />
> The 1.5 version record full sentence, allow natural pause. The 0.2 cut off even on normal sentence, might be more suitable for a drink order machine. The 0.7 cut off on natural pause. 1.5 and 0.7 are better for natural dialogue, with 0.7 sounds like a impatient friend.

## D. Storyboard

<img width="3053" height="2292" alt="image" src="https://github.com/user-attachments/assets/7eec1117-758b-4f6f-8fce-8ad80d10e27e" />

<img width="2818" height="2823" alt="image" src="https://github.com/user-attachments/assets/6dd6f48c-dabc-4b7b-b9a8-40915bcf4bb7" />

<img width="4536" height="8064" alt="IMG_6842" src="https://github.com/user-attachments/assets/5e53de0f-cbac-4230-af69-f7b9f63acef8" />

> On occasion of silence, the VAD should wait up to 5 seconds, then the box will speak on its own, asking "is anyone there?".

## E. Acting out the dialogue

[video](https://youtu.be/IDa1cwQhbnY)

> The dialogue diverge from script when the user ask me to explain which planet I am from, this is something that I did not have a response prepared for, so I have to improvise and guide him to say the things that is in the designed flow.

---

# Lab 3 Part 2

For Part 2, you will redesign the interaction with the speech-enabled device using the data collected, as well as feedback from part 1.

## Instruction to run the code

`bash
cd ~/sphinx-share
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-share.txt
bash speech-scripts/setup.sh
export DEEPSEEK_API_KEY="<fill your API KEY here>"
python3 alien_speak.py
`

## Prep for Part 2

*Document how the system works.*

Storyboard
<img width="4139" height="3104" alt="Storyboard" src="https://github.com/user-attachments/assets/74d86903-65b2-4200-a006-10f616c8e755" />

Rating of drawings
<img width="2268" height="4032" alt="IMG_6897" src="https://github.com/user-attachments/assets/b6c0b396-21bf-4dc2-8a01-b5202f191b6d" />

Camera (pointing at the participant) and speaker
<img width="4536" height="8064" alt="IMG_6898" src="https://github.com/user-attachments/assets/7ef0e65f-cdb3-4e86-b16b-47f69110703d" />

*Include videos or screen captures of both the system and the controller.*


> User study 1 was done in class with Professor and another teammate. Unfortunately, no footage was recorded.
> Here is another footage of complete user study showcasing the system and the controller.

[Footage](https://youtube.com/shorts/SsT0dKgCiVU?feature=share)

## Test the system

Try to get at least two people to interact with your system. (Ideally, you would inform them that there is a wizard *after* the interaction, but we recognize that can be hard.)

Answer the following:

### What worked well about the system and what didn't?
> The rating interface is straightforward and intuitive. We think the experience of describe-and-draw to a machine is an interesting experience, all participants reflects that being "fun". However, the system prompt and routine is not polished such that there is a limited set of hardcoded question and user can't not ask for more challenge when they complete the three questions. A system that work well should allows more extensive interaction. Also, the rating guideline is not clear such that, user displaying the wrong drawing could still receive high rating.

### What worked well about the controller and what didn't?
> The camera work surprisingly well, and the microphone pick up at a larger range than we thought. However, the transcription quality could be improved as we see that a majority of time our voice input is transcribed partially wrong, which is negative toward user experience. The frame rate of camera could be improved so we captured a more information rich footage and enable more natural UX experience. Currently, the system relies on taking three equal-interval (during speech recording) screenshots of the camera input to observe the user.

### What lessons can you take away from the WoZ interactions for designing a more autonomous version of the system?
> In fact, this system here is fully autonomous! However, We imagined there could be more visual instruction so we don't need to remind the participant what to do, and we design the system with rigid protocol for generating drawing quest and rating guideline so it is not limited to the set of hardcoded question right now. In addition, we think the comment that machine gave could be more characteristic to make the system engaging.

### How could you use your system to create a dataset of interaction? What other sensing modalities would make sense to capture?
> This system could decompose the video recording into many information: facial expression of user (their emotion toward system's prompt, system's comment on their drawing, are they comfortable engaging with the system), voice recording (what did the user actually say, sentimental analysis, what is their altitude toward the system and the system's feedback on their drawing, is any part of the system's prompt confusing them) and of course, the drawing they make (how was the quality, did they misinterpret the system's prompt, is the system's judgement fair, is the system bias toward certain visual input). Other sensing modalities that is worth capturing is user's gaze trace, which can be achieve via a eye-tracking device. This device would generate a heatmap of where user is gazing on the screen; this is helpful for improving interface design.
