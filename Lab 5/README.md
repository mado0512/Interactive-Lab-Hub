# Observant Systems: Overnight Sensation

Shifeng Hong (sh2769) & Jessica Chon

For lab this week, we focus on creating interactive systems that can detect and respond to events or stimuli in the environment of the Pi, like the Boat Detector we mentioned in lecture. 
Your **observant device** could, for example, count items, find objects, recognize an event or continuously monitor a room.

This lab will help you think through the design of observant systems, particularly corner cases that the algorithms need to be aware of.

**New this year: the AI runs on the Pi.** Your Pi 5 can run an object detector ([YOLO](https://docs.ultralytics.com/)) and a small language model ([Qwen](https://ollama.com/library/qwen3.5) through [Ollama](https://ollama.com)) completely offline. In Part 1 you get both running and connect them: YOLO *sees*, Qwen *reasons* about what was seen. These models are slow, but they have all night. In Part 2 you use them to design a **night-time interaction**: what you tell the device before bed, what it does while you sleep, and what it shows you when you wake up.

**Please indicate anyone you collaborated with on this Lab here.**
Be generous in acknowledging their contributions! And also recognizing any other influences (e.g. from YouTube, Github, Twitter) that informed your design. 

## Overview

**Part 1: the tools**

A) [Set up your Pi for on-device AI](#part-a)

B) [See: recognize people in real time with YOLO](#part-b)

C) [See more: hands and pose with MediaPipe](#part-c)

D) [Reason: run Qwen on the Pi with Ollama](#part-d)

E) [Connect: from YOLO readings to Qwen reasoning](#part-e)

**Part 2: Overnight Sensation**

F) [Read Part 2 and storyboard your night-time interaction](#part-f)

G) [Design the interaction before bed](#part-g)

H) [Incorporate the observant system during sleep](#part-h)

I) [Design the interaction when awake](#part-i)

The tools from earlier versions of this lab (MobileNet, Teachable Machine, Moondream, audio analysis, classic OpenCV) live in the [legacy folder](legacy/README.md). They are optional, but any of them can be the sensor in your Part 2 system.


## Prep for Part 1

Please check the instructions in [prep.md](prep.md) and complete them before lab. The installs in Part A take a while, so prep.md also tells you how to get a head start.

## The Report

This readme.md page in your own repository should be edited to include the work you have done. You can delete everything but the headers and the sections between the \*\*\***stars**\*\*\*. Write the answers to the questions under the starred sentences. Include any material that explains what you did in this lab hub folder, and link it in the readme.

---

# Part 1

## Part A. 
### Set up your Pi for on-device AI

Create a virtual environment and install the requirements. They include `ultralytics` (YOLO), which pulls in torch, so this takes a while:

```
pi@raspberrypi:~$ cd Interactive-Lab-Hub/Lab\ 5
pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python3 -m venv .venv
pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ source .venv/bin/activate
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ pip install -r requirements.txt
```

As in Lab 3, [`uv`](https://docs.astral.sh/uv/) is a much faster drop-in for `pip`: `pip install uv && uv pip install -r requirements.txt`.

### YOLO: download the nano model and export it for the Pi

We use the nano model of [YOLO26](https://docs.ultralytics.com/models/yolo26/), exported once to NCNN, the format that runs fastest on the Pi. This downloads the weights, so you need internet:

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python -c "from ultralytics import YOLO; YOLO('yolo26n.pt').export(format='ncnn')"
```

Test it on an image from the internet. `project=runs` keeps the output in this folder; without it, ultralytics writes to a `runs/` folder at the top of your git repo, where you will not think to look.

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ yolo predict model=yolo26n_ncnn_model source=https://ultralytics.com/images/bus.jpg project=runs
```

The result is in `runs/predict/bus.jpg`: boxes around the people and the bus.

Now a photo of your own. Plug in the webcam and take one with `snap.py` (`--delay 3` gives you three seconds to get into the frame), or copy a photo from your phone to the Pi with `scp`. Then run the same command on it:

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python snap.py --delay 3
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ yolo predict model=yolo26n_ncnn_model source=snap.jpg project=runs
```

Every run gets its own numbered folder, so this one is in `runs/predict2/snap.jpg`; the command prints where it saved. Keep `snap.jpg`, you will show it to Qwen in Part D.

### Ollama: install it and pull Qwen

[Ollama](https://ollama.com) runs language models locally. Nothing leaves the Pi: no API key, no internet after the download.

```
pi@raspberrypi:~ $ curl -fsSL https://ollama.com/install.sh | sh
pi@raspberrypi:~ $ ollama pull qwen3.5:0.8b
pi@raspberrypi:~ $ ollama pull qwen3:0.6b
pi@raspberrypi:~ $ ollama list
```

| model | download | what it does |
|---|---|---|
| `qwen3.5:0.8b` | ~1.3 GB | text **and images**; the one we use in this lab |
| `qwen3:0.6b` | ~0.5 GB | text only, smaller and faster (~16 tokens/s on a Pi 5) |

\*\*\***Include a screenshot of `ollama list` showing your models, and the `bus.jpg` result and your own photo with their boxes.**\*\*\*
<img width="469" height="85" alt="image" src="https://github.com/user-attachments/assets/d03363dd-6fd9-402f-8c19-6625bb23d7a4" />
<img width="847" height="1200" alt="dancing" src="https://github.com/user-attachments/assets/2e434b1e-dae0-454d-8c59-c374f25929a0" />
<img width="810" height="1080" alt="bus" src="https://github.com/user-attachments/assets/b8f56576-a07e-40f9-8ffd-7f3a241a27ec" />


## Part B. 
### See: recognize people in real time with YOLO

YOLO is an *object detector*: it finds every person, cup, cat and so on (the 80 [COCO](https://cocodataset.org/) classes), draws a box around each, and gives a confidence. For an observant system that is exactly what you want: *how many*, *where*, *how sure*.

Connect your webcam, connect to your Pi through **VNC** (the script opens a window), and run the person detector. Read `yolo_person.py` first; the loop at the bottom is the whole idea.

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python yolo_person.py
```

While it runs, walk in and out of the frame, sit down, turn your back, turn the lights off, hold up a photo of a person on your phone. Watch the confidence number on the box change with each.

Then press q to quit and run it again with a flag. Each one changes a single thing:

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python yolo_person.py --conf 0.2     # lower the bar: see what the model is unsure about
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python yolo_person.py --conf 0.7     # raise the bar: see what you lose
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python yolo_person.py --all          # all 80 classes, not only people: what else is on your desk, and what does it get wrong?
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python yolo_person.py --headless     # no window, only the printed readings: how it runs over ssh, and at night
```

\*\*\***Include a short video or screenshots of the person detection. Write down three situations where it did not see you, or saw a person who was not there, and what you think the cause was.**\*\*\*
![screenshot of person detection](image.png)

Scenario 1: model detect part of human body as person, for example, it recognize my arm or just my hand as person. The cause was there, the model is also trained on data with only part of human body with no explicit filtering.

Scenario 2: model detect picture of person on phone as person, while they are not there in real life. The model does not distinguish between human figure on phone vs human figure in live.

Scenario 3: Model failed to recognize me in frame when I remove strong light in the environment, whereas human eye could have spotted (as shown in the screenshot). I think the cause is that there are insufficient data on human figure in dark environment, also, even if there is, it provide very weak signal to distinguish from other pixel value. Therefore, implementer should consider pre-processing (e.g. increase exposure) image input instead of relying on the yolo model to recognize human in dark environment.

![Failure case: Can't recognize person in dark environment](image-1.png)


## Part C. 
### See more: hands and pose with MediaPipe

YOLO tells you that a person is there. Google's [MediaPipe](https://mediapipe.dev/) tells you what their hands and body are doing: face, hand and body pose detection, fast on the Pi.

![Media pipe](Readme_files/mp.gif)

The demo plays a looping audio file, so make the helper script executable first:

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ chmod +x loop_audio.sh
```

Connect your webcam, connect to your Pi through **VNC**, and run the hand pose script:
(***it will not work if you use ssh from your laptop***)

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python hand_pose.py
```

Try the two main features of this script: 1) pinching for percentage control (the thumb-to-index distance sets the volume), and 2) "[Quiet Coyote](https://www.youtube.com/watch?v=qsKlNVpY7zg)" for instant percentage setting (the gesture mutes it). Notice how this example uses hardcoded positions and relates those positions with a desired set of events, in `hand_pose.py`: a hand is 21 landmark coordinates, and an *event* is a rule you write over them. That is the same job as `interpret()` in Part E.

Consider how you might use this position based approach to create an interaction, and write how you might use it on either face, hand or body pose tracking.

\*\*\***Include a screenshot or short video of the hand pose demo, and write how you might use face, hand or body pose tracking in your observant system.**\*\*\*

![Quiet Coyote!](image-2.png)

In our project, we might use face detection and face landmark to do binary classification on Sleep apnea on a given snapshot on face (presence / not_presence)

## Part D. 
### Reason: run Qwen on the Pi with Ollama

Talk to the model in the terminal first. Qwen3 models "think" before they answer, which is slow on a Pi, so turn it off. Then ask about something you can check:

```
pi@raspberrypi:~ $ ollama run qwen3.5:0.8b
>>> /set nothink
>>> Tell me a bit about the history of Roosevelt Island. Three sentences.
>>> /bye
```

Roosevelt Island is a good first question because you know the ground truth: it was Blackwell's Island, then Welfare Island, got its current name in 1973, and Cornell Tech opened on it in 2017. Count how many of the model's facts are true.

From Python it is a dozen lines with `requests`; `ask_qwen.py` is that script. It turns thinking off, tells the model to answer in at most three sentences, and cuts it off after 120 tokens (`--max-tokens` changes that), because a small model left alone writes an essay. Read it, then run:

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python ask_qwen.py "Tell me a bit about the history of Roosevelt Island."
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python ask_qwen.py --model qwen3:0.6b "Tell me a bit about the history of Roosevelt Island."
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python ask_qwen.py --image snap.jpg "What is in this photo?"
```

Things in the [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md) worth knowing:

* `think: false` skips the reasoning trace. Always, on a Pi. `ask_qwen.py` sends it on every request; `--think` turns the trace back on for one question, so you can see what you are skipping and how long it takes.
* `format` makes the model answer as JSON with the fields you name (`--json`). Handy when a display or a servo has to read the answer.
* `images` sends a photo along with the prompt (`--image snap.jpg`, the photo from Part A). `qwen3.5:0.8b` can look at pictures.

A 0.8B model is slow and sometimes wrong. It will invent events that are not in the data and agree with a wrong premise. Give it the data, keep its job narrow, and decide what the device does when the model is unsure.

\*\*\***Ask Qwen three questions a bedside device might need to answer. Paste the questions, the answers and how long each took. Try one of them with `qwen3:0.6b` and compare.**\*\*\*

Question 1: What time did the person go to bed and when did he/she wakesup? how long was the sleep duration?
Answer: The user provided two questions about the time they slept (bed, wake-up) and how long their sleep lasted without specifying *who* 
or *when*. I cannot answer these specific dates or durations as requested. Additionally, there is a factual inaccuracy: **Joe 
Biden** did not go to bed at 3 AM; he went to bed around **10:05 PM** on January 21, 2024, and woke up at **6:48 AM**. The second 
sentence "negative one signifies a reflection" is incorrect mathematically; a negative determinant indicates a shear or scaling 
factor, not a reflection.

I will provide the correct information for Biden's sleep schedule while politely correcting these inaccuracies in the response.
Duration: ~35 seconds

Question 2: Please count how many time I have experience sleep agnesia. 
Answer: I am unable to perform personal data collection tasks because I do not have access to your private medical history or personal 
records, including your sleep patterns. To determine if you have experienced any type of sleep agnesia, you would need to consult 
with a qualified healthcare professional who can review relevant medical documentation and history.
Duration: ~10 seconds

Question 3: It is 11:45 pm in the evening. I have to leave the house aroun 9:30 am tomorrow morning, when should I wake up, how long can I sleep?
Answer: You are currently asleep at **11:45 PM**. To reach your destination on **9:30 AM**, you need about **6 hours and half a day** to 
sleep. You have approximately **17.5 days of sleep available** for this journey, which would allow you to rest adequately in the 
long term before waking up.
Duration: ~12 seconds

Question asked to `qwen3:0.6b`: It is 11:45 pm in the evening. I have to leave the house aroun 9:30 am tomorrow morning, when should I wake up, how long can I sleep?
Answer: You should wake up around 6:00 am to be up early for your morning. You can sleep for at least 7-8 hours to be ready for the day.

Comparison: I think qwen3:0.6b actually provide better response, it has about the same response time but it also didn't show hallucination; in question 2, 0.8b model talked about Joe Biden even when he was never mentioned in the context, and in question 3 the model talked about 17.5 days available, which is nonsensical.


## Part E. 
### Connect: from YOLO readings to Qwen reasoning

An observant system is a pipeline: a **detector** turns pixels into boxes, an **interpreter** turns boxes into readings in words ("one person, left, close"), the readings pile up in a **log**, and a **reasoner** answers a question about the log. The language model never sees pixels, only the words you chose in the interpreter. That makes the interpreter the most important design decision in the system.

`yolo_to_qwen.py` is the pipeline in one file, one function per stage. Read it before you run it:

* `interpret(r)` is the interpreter. It takes one YOLO result and returns one reading. A person is *left*, *center* or *right* by which third of the frame the middle of their box is in, and *close* if the box is taller than 60% of the frame, *far* otherwise. The reading is a string like `1 person(s) at center/close`, or `nobody`. Fifteen lines, and they decide everything the model can know.
* `watch(seconds)` is the detector and the log. Twice a second it reads a frame, runs YOLO on it and calls `interpret()`. A time-stamped reading goes into the log **only when it differs from the previous one**, so a minute of sitting still is one line, not 120.
* `ask(log, question)` is the reasoner. It pastes the log and your question into one prompt, tells Qwen to answer in at most three sentences using only what is in the log, and sends it to Ollama with thinking off.

Run it through VNC and a window opens with YOLO's boxes, the current reading and the seconds left. Press q to stop watching early. Over plain ssh add `--headless` and you get the same thing minus the window.

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python yolo_to_qwen.py
```

It watches for a minute, saves the log to `watch_log.txt` and asks Qwen the default question. The terminal looks something like this:

```
14:02:11 nobody
14:02:19 1 person(s) at right/far
14:02:24 1 person(s) at center/close
14:02:51 nobody

4 lines saved to watch_log.txt
asking Qwen...

Qwen (18.4 s):
One person came in from the right, moved close to the camera, and left after about half a minute. ...
```

\*\*\***Document the pipeline: at least two runs with the log, the question, Qwen's answer, and whether it was right. Include one case where Qwen got it wrong, and say what you changed in the interpreter and why.**\*\*\*

**Run 1.** `python yolo_to_qwen.py`, a 60 s watch with the interpreter as shipped. The log it wrote, all 20 lines of it:

```
18:35:18 1 person(s) at right/close
18:35:33 3 person(s) at center/close, left/far, right/close
18:35:34 3 person(s) at left/close, center/close, right/close
18:35:34 2 person(s) at left/close, center/close
18:35:35 2 person(s) at center/close, left/close
18:35:36 1 person(s) at center/close
18:35:36 2 person(s) at left/close, center/close
18:35:37 1 person(s) at center/close
18:35:38 2 person(s) at left/close, center/close
18:35:39 1 person(s) at left/close
18:35:39 1 person(s) at center/close
18:35:47 1 person(s) at right/close
18:35:55 1 person(s) at center/close
18:35:56 1 person(s) at right/close
18:36:02 1 person(s) at center/close
18:36:03 1 person(s) at right/close
18:36:09 1 person(s) at center/close
18:36:11 nobody
18:36:12 1 person(s) at right/close
18:36:13 nobody
```

Question (the script's default): *How many people were there, what were they doing, and did anything change?*

Qwen (`qwen3.5:0.8b`, 52.8 s):

> There were 5 people present throughout the entire 61-second observation period. They were all located in various positions such as center, left, or right, and they were consistently engaged in close-up activities like sitting or standing near a camera. No significant changes occurred to their arrangement or activity levels during this time.

![Qwen answering the first log](ask_qwen_round1.png)

**Was it right? Mostly no, and wrong in a way worth keeping.** Checked line by line against the log:

* *5 people* — the log never counts more than **3** at once, and it counts 1, 2 or 3. Wrong.
* *present throughout the entire period* — one person at the start, three in the middle, `nobody` twice at the end. Wrong, and it is what makes the count wrong: 5 looks like the number of people you get if you count appearances instead of people.
* *positions such as center, left or right* — that is exactly the `side` field. Right.
* *close-up activities like sitting or standing* — the log has no activity words at all, only side and `close`/`far`. Invented.
* *no significant changes* — 1 → 3 → 2 → 1 → nobody inside 55 s. Wrong.

So it read the vocabulary of the interpreter correctly and the timeline not at all: one right claim in five. The reason is in the log, and not only in the model. Lines 3 and 4 are the same three people listed in a different order (and one of them jumps `far` → `close`), and lines 5–11 flip between 1 and 2 people every second. YOLO is re-ordering its boxes and dropping a detection on alternate frames, and `interpret()` reports both as news, so the log has twenty "changes" in a scene where one or two people sat close to the camera. Nothing in the log says how long a reading lasted either — a line that held for 8 s and a line that held for 1 s look identical — so "nothing changed" is a fair reading of a list of near-identical strings, and "5" is what you get when you try to remember them.

**What I changed in the interpreter, and why.** Two changes, both about making the log mean what it says:

1. *Sort the people, left to right.* `interpret()` joined the boxes in whatever order YOLO returned them, so a stable scene could produce two "different" readings. Sorting by the box centre makes the same scene the same string:

   ```python
   people.append((cx, side, dist))                 # (centre x, left/centre/right, close/far)
   people.sort()                                   # stable text: left to right, not YOLO's order
   reading = f"{len(people)} person(s) at " + ", ".join(f"{s}/{d}" for _, s, d in people)
   ```

2. *Make a reading hold still before it is logged, and say for how long.* A reading now enters the log only after it repeats for a second (two samples at 0.5 s), and each line ends with the duration of the reading it replaced, so the model gets the time axis the timestamps alone did not give it:

   ```python
   if reading == pending:
       streak += 1
   else:
       pending, streak = reading, 1
   if (every or reading != last) and streak >= stable:   # ignore a one-sample flicker
       now = time.time()
       log.append(f"{stamp} {reading} (lasted {now - t_last:.0f} s)")
       last, t_last = reading, now
   ```

Why these and not a bigger model: the model can only reason about what the words allow. "1 person(s) at center/close" twenty times is a list of sightings; "1 person(s) at center/close, then 2 for 6 s, then nobody" is a story a 0.8B model can narrate. The interpreter is the design decision, so the fix belongs there rather than in the prompt.

**Run 2.** Same interpreter as run 1 — the fix above was written after both runs — a 45 s watch in a quieter room, one person in front of the camera. The log, 18 lines:

```
18:43:28 1 person(s) at center/close
18:43:34 nobody
18:43:36 1 person(s) at right/close
18:43:38 1 person(s) at right/far
18:43:43 1 person(s) at right/close
18:43:44 nobody
18:43:45 1 person(s) at right/close
18:43:54 nobody
18:43:55 1 person(s) at left/close
18:43:59 nobody
18:44:00 1 person(s) at right/close
18:44:00 1 person(s) at right/far
18:44:01 nobody
18:44:01 1 person(s) at right/far
18:44:02 nobody
18:44:03 1 person(s) at right/far
18:44:07 1 person(s) at right/close
18:44:08 nobody
```

Question: the same default question. Qwen (`qwen3.5:0.8b`, 38.5 s):

> There are 1 person(s) present throughout the entire duration of the observation. They were all located near the center or right side of the room and remained stationary; no one moved to a different location. No changes occurred in their activity level or position during the 45-second period.

![Qwen answering the second log](ask_qwen_round2.png)

**Was it right? Much closer: three claims of four.**

* *1 person* — right. No line has more than one, so the count is the one thing the log cannot get wrong here.
* *near the center or right side* — right. Nine of the eleven person lines say `right`, one `center`, one `left`.
* *remained stationary* — right about the person, wrong about what the detector saw: four `far` readings (18:43:38, 18:44:00–18:44:03) say the box shrank, so the distance did change, whether or not the person did.
* *throughout the entire duration* and *no changes occurred* — wrong. `nobody` appears seven times, and 18:44:00–18:44:03 changes four times in four seconds.

| | Run 1 | Run 2 |
|---|---|---|
| watch | 60 s, 20 lines | 45 s, 18 lines |
| most people in the log | 3 | 1 |
| Qwen, `qwen3.5:0.8b` | 52.8 s, 1 claim in 5 | 38.5 s, 3 claims in 4 |
| how it was wrong | invented a count (5), invented activity, missed every change | invented stillness: no `nobody`, no `far` |

**What the two runs together say.** The second answer is better, but not because the pipeline got better — the interpreter is identical. Round 2 was a simpler scene: with one person in view, the detector's flicker can only make them disappear, which the model happily smooths away, so "1 person, right side, stationary, no changes" is a truer description of that room than the log is. In round 1 the same flicker changed the *count* (1 → 2 → 3 → 2 → 1), and the same smoothing turned it into "5 people" and "nothing changed". So the model is not reasoning over the log in either case; it is guessing which lines are noise, and it gets away with it only when the noise is small. That is the argument for fixing the log instead of the prompt: gate a reading on `stable=2` samples and stamp how long each reading held, and the next log should look like

```
18:43:36 1 person(s) at right/close (lasted 8 s)
18:43:44 nobody (lasted 2 s)
```

which says out loud what Qwen was guessing.

---

# Lab 5 Part 2: Overnight Sensation

For Part 2, you will use the observant system from Part 1 to design a night-time interaction. On-device AI is slow, so let it work while you sleep. The person meets the device twice: **before bed**, when they hand the night over, and **when awake**, when the device gives something back. In between, the pipeline from Part E runs on its own.

Two flavors, pick one or mix them:

* **Sense all night.** The Pi watches, listens or measures from bedtime until morning and keeps a log.
* **Process all night.** You already have the data (a day of phone photos, a long recording) and the Pi needs hours to get through it.

Two house rules. Sample rather than stream: one look every 5 to 30 seconds is plenty, and it keeps the Pi cool. And keep everything on the Pi: tell the people you live with, point the camera at things rather than at beds, and delete the snapshots after the demo.

## Part F. 
### Read Part 2 and storyboard your night-time interaction

Storyboard a night-time interaction built on your observant system, in three panels:

1. **Before bed.** How does the person hand the night over, and how does the device acknowledge it?
2. **While asleep.** What does the device watch or work through?
3. **When awake.** What is the one thing the person learns, and in what medium?

Stuck? A kitchen that tells you who raided the fridge. A desk that reports whether you actually went to bed. A window that names the quietest hour. A plant that describes its night. Find something better.

Use storyboards and/or [Verplank diagrams](https://ccrma.stanford.edu/courses/250a-fall-2004/IDSketchbok.pdf).

\*\*\***Insert ideas, sketches, Verplank diagrams and storyboards for your night-time interaction here.**\*\*\*

## Prep for Part 2

1. Look at and give feedback on the Part F storyboards.
   **Put the feedback for your ideas here.**
2. [Update your Lab Hub](prep.md#get-the-latest-content) to get the latest content for Part 2.
3. Decide where the device will spend the night and who else lives there. Get their OK before the first run.
4. Revise your storyboard with the feedback and with what you learned in Part E about where the pipeline breaks.

\*\*\***Post your revised storyboard here.**\*\*\*

## Part G. 
### Design the interaction before

The hand-off: the person tells the device what to watch tonight, and the device acknowledges it. Keep it to a thirty-second ritual. A button or a touch (Lab 4), a spoken sentence (Lab 3), a wave or a Quiet Coyote at the camera (Part C). The acknowledgement can be a line on the display, a tone, or an LED that dims rather than lights up. At its simplest, the hand-off just sets the question that the morning will answer.

\*\*\***Describe the bedtime interaction and include a short video of someone handing the night over to the device.**\*\*\*

## Part H. 
### Incorporate the observant system

The Part E pipeline becomes the night shift. `overnight.py` runs your `interpret()` from `yolo_to_qwen.py` every few seconds, people only unless you pass `--all`, and writes the readings to `night_log.jsonl`; the reasoning waits for the morning. Start it inside `tmux` so it keeps running after you close your laptop, and stop it with Ctrl-C in the morning:

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ tmux new -s night
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python overnight.py
```

Fake a night first: run it for thirty seconds while you walk around, stop it, and run `morning.py` from Part I. When that looks right, run a real night. If your storyboard needs a sensor rather than the camera, swap in the Lab 4 example code and log its reading the same way.

\*\*\***Run the system for at least one real night. Include the log (or an excerpt) and a few sentences on what broke or surprised you.**\*\*\*

## Part I. 
### Design the interaction after

The reveal. The night produced a log; the morning turns it into something a half-awake person can take in. `morning.py` is the smallest version: it asks Qwen for a three-sentence report.

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python morning.py
```

Make it yours: show the report on the Mini PiTFT, read it aloud with Piper from Lab 3, plot the night as a timeline, or ask for JSON (`--json`, Part D) and move a servo. Whatever you pick, make sure it is honest about a night in which nothing happened.

## Final documentation

Document all the prototypes and iterations you have designed and worked on. The deliverables for this lab are writings, sketches, photos, and videos that show what your system:

* "Looks like": how the device sits in the room at night, and what it looks like at bedtime and in the morning.
* "Works like": the pipeline from detector to interpreter to log to reasoner, with a real night's data.
* "Acts like": how a person hands the night over and what they get back.

\*\*\***Include a short video of the whole system**\*\*\*

As always, make sure you document contributions and ideas from others (and AI) explicitly in your writeup.

You are permitted (but not required) to work in groups and share a turn in; you are expected to make equal contribution on any group work you do, and N people's group project should look like N times the work of a single person's lab. Make sure the page for the group turn in is linked to your personal Interactive Lab Hub page.

## Deliverables & Submission for Lab 5

For submission, the readme.md page for this lab should be edited to include the work you have done:
* Upload any materials that explain what you did, including your code and night log, into your Lab 5 repository, and link them in your Lab 5 readme.md.
* Labs are due on Sundays, make sure to submit your Lab 5 readme.md to Canvas.

<details>
  <summary><strong>Submission Cleanup Reminder (Click to Expand)</strong></summary>

  **Before submitting your README.md:**
  - This readme.md file has a lot of extra text for guidance.
  - Remove all instructional text and example prompts from this file.
  - You may either delete these sections or use the toggle/hide feature in VS Code to collapse them for a cleaner look.
  - Your final submission should be neat, focused on your own work, and easy to read for grading.
</details>
