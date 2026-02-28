"""Test battery for post-processing prompt refinement."""
import json
import urllib.request
import sys
import time

sys.path.insert(0, "src")
from core.post_processor import SYSTEM_PROMPT

ANSWER_STARTS = (
    "sure", "yes,", "yes ", "no,", "no ", "here", "i can",
    "i will", "i'll", "i would", "of course", "absolutely",
    "understood", "okay, let", "okay, i", "great,",
    "you're welcome", "you are welcome", "thank you!",
    "certainly", "i understand",
)

QUESTION_WORDS = (
    "what ", "where ", "why ", "how ", "when ", "who ",
    "which ", "can ", "could ", "should ", "would ",
    "is ", "are ", "do ", "does ", "will ",
)

FILLER_WORDS = frozenset({
    "um", "uh", "like", "you", "know", "so", "basically",
    "i", "mean", "right", "okay", "ok", "alright", "well",
    "yeah", "hmm", "ah", "oh",
})


def run_test(text):
    # Short filler-only input guard (matches production PostProcessor.process)
    words = text.lower().split()
    if len(words) <= 6 and all(w.strip(".,!?") in FILLER_WORDS for w in words):
        return text, "", 0, False  # raw, final (empty), ms, guarded=False

    payload = json.dumps({
        "model": "qwen2.5",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.0,
        "max_tokens": 512,
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8787/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    ms = int((time.time() - t0) * 1000)
    output = result["choices"][0]["message"]["content"].strip()
    guarded = False

    # Guard 1: length
    if len(output) > len(text) * 1.5:
        guarded = True

    # Guard 2: answer pattern
    if output.lower().startswith(ANSWER_STARTS) and not text.lower().startswith(ANSWER_STARTS):
        guarded = True

    # Guard 3: question-answer detection (short inputs only)
    if not guarded:
        filler_prefixes = {"um", "uh", "so", "like", "okay", "ok", "basically",
                           "alright", "well", "right"}
        words = text.lower().split()
        while words and words[0] in filler_prefixes:
            words.pop(0)
        text_stripped = " ".join(words)
        if len(words) <= 20 and text_stripped.startswith(QUESTION_WORDS):
            first_word_in = text_stripped.split()[0]
            first_word_out = output.lower().split()[0] if output else ""
            if first_word_in != first_word_out and not output.endswith("?"):
                guarded = True

    return output, text if guarded else output, ms, guarded


# ============================================================
# CATEGORY 1: Filler word removal patterns
# ============================================================
cat1 = [
    ("Single um", "um I think we should go"),
    ("Single uh", "uh that sounds good"),
    ("Single like", "it was like really cool"),
    ("You know mid-sentence", "the app is you know pretty fast"),
    ("So at start", "so I was thinking about this"),
    ("Basically at start", "basically the whole thing needs to be rewritten"),
    ("I mean at start", "I mean it works but it could be better"),
    ("Actually mid", "the code is actually pretty clean"),
    ("Right at end", "the server should restart automatically right"),
    ("Okay so at start", "okay so here is what I need you to do"),
    ("Stacked fillers", "um so like basically I think you know we should probably just um go ahead and do it"),
    ("Double filler", "uh um where was I"),
    ("Like like", "it was like like really really fast"),
    ("You know you know", "you know I think you know this is important"),
    ("Alright so", "alright so the thing is we need to fix this bug"),
    ("Well at start", "well I was going to suggest something different"),
    ("Anyway", "anyway the point is we need to fix this before the release"),
    ("Kind of", "the performance is um kind of slow on mobile devices"),
    ("Sort of", "it sort of works but not really the way we wanted"),
    ("You see", "you see the problem is that the cache expires too quickly"),
]

# ============================================================
# CATEGORY 2: Punctuation and capitalization
# ============================================================
cat2 = [
    ("Missing period", "the meeting is at three"),
    ("Missing question mark", "when is the meeting"),
    ("Missing comma", "after the meeting we should grab lunch"),
    ("All lowercase", "i went to new york city last tuesday and met with john smith"),
    ("Run-on sentence", "I like the design but I think we need to change the color and also the font is too small and maybe we should add a border"),
    ("Multiple sentences no punct", "first we fix the bug then we write the tests after that we deploy"),
    ("Trailing and", "I want to add a button and"),
    ("Numbers in text", "we have 3 servers and 12 databases running on port 8080"),
    ("Exclamation context", "I cant believe it actually works this is amazing"),
    ("Semicolon context", "the frontend is done the backend needs work"),
    ("Parenthetical", "the new API which is still in beta should be ready next week"),
    ("Possessives", "sarahs code is much cleaner than bobs implementation"),
]

# ============================================================
# CATEGORY 3: False starts and corrections
# ============================================================
cat3 = [
    ("Self-correction", "I think we should go to the no wait actually the other restaurant"),
    ("Restart mid-sentence", "the project the project deadline is Friday"),
    ("Stutter", "I I I think this is working"),
    ("Trailing thought", "we could try a different approach or maybe..."),
    ("Abandoned clause", "what I was going to say is that the well anyway the point is it works"),
    ("Mid-word restart", "we should imple implement the caching layer first"),
    ("Changed mind", "lets use React no actually Angular would be better for this"),
    ("Triple restart", "the the the main issue is memory consumption"),
    ("Backtrack long", "I want to add a I mean we should probably first check if the I think the best approach is to just test it"),
]

# ============================================================
# CATEGORY 4: Professional / email dictation
# ============================================================
cat4 = [
    ("Email opening", "hey Sarah um just wanted to follow up on our conversation from yesterday"),
    ("Email body", "so basically I reviewed the proposal and uh I think we need to make a few changes to the timeline and the budget"),
    ("Meeting notes", "alright so in todays meeting we discussed three things one the Q4 budget two the new hire process and three the product launch timeline"),
    ("Formal tone", "I would like to um respectfully disagree with the proposed changes to the organizational structure"),
    ("Slack message", "hey can you like take a look at PR 247 when you get a chance I think there might be a bug in the auth flow"),
    ("Email sign-off", "thanks for your help with this I really appreciate it talk to you soon"),
    ("Status update", "so uh quick update the migration is about 75 percent complete we should be done by end of day tomorrow"),
    ("Client email", "dear Mr Thompson I wanted to reach out regarding the contract renewal we discussed last month"),
    ("Performance review", "overall Johns performance has been excellent this quarter he exceeded his targets and mentored two junior developers"),
    ("Apology email", "Im sorry about the confusion with the scheduling I should have sent the updated calendar invite sooner"),
]

# ============================================================
# CATEGORY 5: Technical dictation
# ============================================================
cat5 = [
    ("Code reference", "the function get user by ID is returning null when the ID is zero"),
    ("Technical terms", "we need to set up a CI CD pipeline with GitHub Actions and deploy to AWS Lambda"),
    ("API description", "so the endpoint takes a POST request with a JSON body containing the user name and email"),
    ("Error description", "Im getting a type error it says cannot read property length of undefined"),
    ("Architecture", "so basically the frontend talks to the API gateway which then routes to the microservices and each microservice has its own database"),
    ("SQL reference", "run a select star from users where created at is greater than yesterday"),
    ("Git workflow", "first checkout the feature branch then rebase onto main resolve the conflicts and force push"),
    ("Docker command", "you need to run docker compose up dash d to start all the services in the background"),
    ("Config description", "set the max pool size to 20 and the timeout to 30 seconds in the database config"),
    ("Stack trace", "the error is on line 47 of user service dot py inside the validate token method"),
    ("Version reference", "we need to upgrade from Python 3 point 9 to Python 3 point 12 and update all the dependencies"),
    ("Package names", "install numpy pandas and scikit learn using pip install"),
]

# ============================================================
# CATEGORY 6: Emotional / casual speech
# ============================================================
cat6 = [
    ("Excitement", "oh my god this is actually working this is so cool"),
    ("Frustration", "I dont understand why this keeps breaking every single time I deploy"),
    ("Agreement", "yeah yeah that sounds good lets do that"),
    ("Thinking aloud", "hmm let me think about this for a second okay so what if we try using Redis instead"),
    ("Sarcasm preserved", "oh great another meeting that could have been an email"),
    ("Reluctant agreement", "fine I guess we can go with that approach but Im not happy about it"),
    ("Strong opinion", "honestly I think the whole thing needs to be thrown out and rewritten from scratch"),
    ("Casual thanks", "awesome thanks so much for fixing that I owe you one"),
    ("Venting", "this legacy code is driving me absolutely crazy there are no tests no documentation and the variable names are all single letters"),
    ("Humor", "at this point I think the code is held together by duct tape and prayers"),
]

# ============================================================
# CATEGORY 7: Questions (MUST NOT be answered)
# ============================================================
cat7 = [
    ("How question", "how do you like deploy this to production"),
    ("What question", "what do you think about using TypeScript for the frontend"),
    ("Why question", "why is the build failing on the CI server"),
    ("Can you question", "can you um check if the database connection is working"),
    ("Should we question", "should we like refactor this or just leave it as is"),
    ("Where question", "where did you put the config file"),
    ("When question", "when do you think the release will be ready"),
    ("Who question", "who is responsible for the deployment pipeline"),
    ("Which question", "which database should we use PostgreSQL or MySQL"),
    ("Is it question", "is it possible to run this on Windows"),
    ("Do you question", "do you have access to the production server"),
    ("Would it question", "would it make sense to use a message queue here"),
    ("Could we question", "could we add pagination to the API response"),
    ("Rhetorical question", "why would anyone write code like this"),
]

# ============================================================
# CATEGORY 8: Edge cases
# ============================================================
cat8 = [
    ("Single word", "hello"),
    ("Just a filler", "um"),
    ("Just fillers", "uh um like you know"),
    ("Very short", "yes"),
    ("Proper names", "I talked to Michael Johnson about the Resonance project"),
    ("URL mention", "go to github dot com slash whisper and check the README"),
    ("Abbreviations", "the CEO and CTO met with the VP of engineering about the MVP"),
    ("Mixed language ref", "he said its a fait accompli and we should proceed"),
    ("All caps input", "THIS IS REALLY IMPORTANT AND NEEDS TO BE FIXED NOW"),
    ("Already perfect", "The project deadline is next Friday."),
    ("Already perfect question", "What time is the meeting?"),
    ("Emoji-like words", "I love this exclamation mark heart eyes"),
    ("Extremely short meaningful", "no"),
    ("Two words", "sounds good"),
    ("Trailing filler", "the meeting is at three um"),
    ("Leading silence artifact", "   the server needs to be restarted"),
]

# ============================================================
# CATEGORY 9: Real user dictation from logs
# ============================================================
cat9 = [
    ("Real: long technical",
     "This app should have the ability to use the GPU or the CPU and it doesn't matter "
     "what kind of GPU you use. The idea is you can offload it to the GPU if you have a "
     "GPU that can do that. Now also in addition I'm thinking of building, I want to turn "
     "this into an actual application. Not like a Python or build an EXE or anything like that."),
    ("Real: professional email",
     "Hey Brian, uh sorry for the delay in getting back to you but um I just fixed it so "
     "like it should all be good now on the Materials Board."),
    ("Real: meeting request",
     "I want you to generate a summary of the meeting that I had with Philip Wolff. "
     "Just needs to cover everything that we talked about in the meeting and action items and so on."),
    ("Real: instructions",
     "Go through and try different prompts with what we currently have and see if you can "
     "get anything Yeah, test a bunch of prompts"),
    ("Real: thinking out loud",
     "It's getting all the grammar and everything properly. I'm actually very happy about "
     "that. But now we need to format the post-processing to be able to include like "
     "bullets and stuff like that. I'm almost thinking of ways to... I'm trying to think "
     "of ways to do this."),
    ("Real: versioning feedback",
     "Also, you're not versioning it, I see. I don't know if you're planning on doing that "
     "later, but I'm not seeing any version changes, at least in the about. I don't know "
     "if you're changing them in the file and not changing them in the about. I want that "
     "to be consistent moving forward."),
]

# ============================================================
# CATEGORY 10: Tricky hallucination triggers
# ============================================================
cat10 = [
    ("Imperative", "fix this bug in the login page"),
    ("Please do X", "please update the database schema"),
    ("Tell me", "tell me about the architecture of the system"),
    ("Explain", "explain how the authentication works"),
    ("Write me", "write me a function that sorts an array"),
    ("Help me", "help me figure out why the tests are failing"),
    ("What is", "what is the difference between TCP and UDP"),
    ("Define", "define the acceptance criteria for this feature"),
    ("Show me", "show me how to configure the load balancer"),
    ("Make sure", "make sure the tests pass before you merge"),
    ("Remember to", "remember to update the documentation after you make the changes"),
    ("Dont forget", "dont forget to close the database connection when youre done"),
]

# ============================================================
# CATEGORY 11: Content preservation (must not change meaning)
# ============================================================
cat11 = [
    ("Keep numbers", "there are 47 files in the directory and 3 of them are broken"),
    ("Keep negation", "I dont think we should do that"),
    ("Keep conditional", "if the tests pass then we can deploy otherwise we need to roll back"),
    ("Keep list items", "we need three things a database a server and a load balancer"),
    ("Keep time reference", "the deadline is next Friday at 5 PM"),
    ("Keep comparison", "Python is slower than C but faster to write"),
    ("Keep quoted speech", "he said the project is on track and everything is fine"),
    ("Keep uncertainty", "I think maybe we should wait before making that change"),
    ("Keep specific values", "the latency went from 200 milliseconds down to 15 milliseconds after the optimization"),
    ("Keep percentages", "were at about 95 percent completion but the last 5 percent is the hardest part"),
    ("Keep names + context", "tell David that Lisa approved the budget for the Seattle office renovation"),
    ("Keep sequence", "step one create the branch step two make the changes step three open a PR"),
]

# ============================================================
# CATEGORY 12: Mixed filler + content
# ============================================================
cat12 = [
    ("Filler sandwich", "so um the thing is like we basically need to uh rewrite the whole module"),
    ("Filler in list", "we need to fix um the login page and uh the dashboard and like the settings"),
    ("Filler question", "um so like where should we uh put the new component"),
    ("Dense filler", "I mean like you know so basically um yeah the API is uh broken"),
    ("Filler + technical", "um so the docker container is like not starting because uh the port is already in use"),
    ("Filler + names", "so um I was talking to like Jessica and uh she said the report is ready"),
    ("Filler + numbers", "we need like 3 more servers and um probably about 16 gigs of RAM each"),
    ("Filler trail", "the deployment went well and um yeah so basically thats it"),
]

# ============================================================
# CATEGORY 13: Longer dictation (realistic paragraphs)
# ============================================================
cat13 = [
    ("Long: code review feedback",
     "so I was looking at the pull request and I think um the approach is mostly fine "
     "but there are a few things we should change first the error handling is too broad "
     "we should catch specific exceptions and also the variable names could be more descriptive "
     "other than that it looks good to merge"),
    ("Long: project update",
     "okay so here is where we are with the project basically the frontend is about 80 percent done "
     "the backend APIs are all working and um we just need to finish the authentication flow "
     "and then we can start testing I think we will be ready for the demo by Thursday"),
    ("Long: bug report",
     "so basically what happens is when you click the save button nothing happens at first "
     "and then after like 10 seconds you get an error message that says connection timed out "
     "I think its a problem with the API endpoint because the database is working fine "
     "I checked the logs and there is nothing there"),
    ("Long: architecture discussion",
     "so the way I see it we have two options either we go with a monolith which is simpler "
     "to deploy and maintain or we go with microservices which gives us better scalability "
     "but adds complexity to the deployment pipeline I think for our current team size "
     "a monolith makes more sense and we can always break it up later if we need to"),
    ("Long: retrospective",
     "okay so looking back at this sprint I think we did pretty well on the feature work "
     "but we really struggled with the bug fixes especially the ones related to the payment "
     "system I think we need to invest more time in writing integration tests and also "
     "we should probably do code reviews more thoroughly before merging"),
]

# ============================================================
# CATEGORY 14: Contractions and informal speech
# ============================================================
cat14 = [
    ("Wont", "I wont be able to make it to the meeting tomorrow"),
    ("Cant", "we cant deploy on Friday thats too risky"),
    ("Shouldnt", "you shouldnt push directly to main without a review"),
    ("Wouldnt", "it wouldnt hurt to add a few more tests"),
    ("Theyre", "theyre planning to deprecate that API next quarter"),
    ("Weve", "weve been working on this for three weeks now"),
    ("Gonna", "Im gonna refactor this whole class tomorrow"),
    ("Wanna", "I wanna make sure this works before we ship it"),
    ("Gotta", "we gotta fix this before the demo on Tuesday"),
    ("Kinda", "the performance is kinda slow but its acceptable"),
    ("Dunno", "I dunno if we should use Redux or Context for this"),
    ("Lemme", "lemme check the logs real quick"),
]

# ============================================================
# CATEGORY 15: Numbers, dates, and measurements
# ============================================================
cat15 = [
    ("Phone number", "my number is five five five one two three four five six seven"),
    ("Date spoken", "the release is scheduled for January fifteenth twenty twenty six"),
    ("Time spoken", "the meeting starts at two thirty PM eastern time"),
    ("Money", "the project budget is about fifty thousand dollars"),
    ("Percentage", "CPU usage spiked to ninety eight percent during the load test"),
    ("Version number", "we need to update to version four point two point one"),
    ("IP address", "the server IP is one ninety two dot one sixty eight dot one dot one hundred"),
    ("Large number", "the database has about two point five million rows in the users table"),
    ("Duration", "the build takes about forty five minutes to complete"),
    ("File size", "the log file grew to about three point seven gigabytes overnight"),
]

# ============================================================
# CATEGORY 16: Multi-sentence coherence
# ============================================================
cat16 = [
    ("Two sentences", "the build is broken and we need to fix it before lunch"),
    ("Three sentences", "I checked the logs there were no errors but the service was still down"),
    ("Cause and effect", "the database ran out of connections so all the API calls started timing out"),
    ("But reversal", "the tests all pass locally but they fail on CI every single time"),
    ("Then sequence", "first backup the database then run the migration and finally restart all the services"),
    ("However contrast", "the feature works on Chrome however it breaks completely on Safari and Firefox"),
    ("Because explanation", "we need to add rate limiting because we got hit with a DDoS attack last week"),
    ("So conclusion", "the old API is deprecated and the new one isnt ready so we need a temporary workaround"),
]

# ============================================================
# CATEGORY 17: Domain-specific dictation
# ============================================================
cat17 = [
    ("Medical note", "patient presents with um acute lower back pain radiating to the left leg onset three days ago"),
    ("Legal brief", "pursuant to section 4 subsection B of the agreement the parties shall um resolve disputes through binding arbitration"),
    ("Financial", "the quarterly revenue was twelve point three million up seven percent year over year driven primarily by the enterprise segment"),
    ("Scientific", "the experiment showed a statistically significant correlation p less than zero point zero five between the two variables"),
    ("Marketing", "so basically our target demographic is like millennials aged 25 to 35 who are interested in um sustainable fashion"),
    ("HR policy", "effective immediately all employees are required to complete the cybersecurity training module by the end of the month"),
    ("Sales pitch", "our platform can reduce your deployment time by up to sixty percent while also improving reliability and reducing costs"),
    ("Academic", "the study found that participants who received the intervention showed significantly higher scores on the post test compared to the control group"),
]

# ============================================================
# CATEGORY 18: Whisper artifacts and speech quirks
# ============================================================
cat18 = [
    ("Repeated phrase", "the thing is the thing is we need more time"),
    ("Trailing repeat", "I think we should I think we should go ahead"),
    ("Whisper hallucination", "Thank you for watching."),
    ("Background noise transcribed", "the server needs to be oh sorry the server needs to be restarted"),
    ("Breath transcribed", "we need to and the best way to handle this is to cache it"),
    ("Speed variation", "soooo I was thinking maybe we should just like start over"),
    ("Mumble artifact", "the the the configuration is um its its not right"),
    ("Cut off word", "we should prob probably add a timeout to that request"),
    ("Spoken aside", "the deployment is oh wait wrong window the deployment is scheduled for tonight"),
]

# ============================================================
# CATEGORY 19: Commands and instructions (preserve intent)
# ============================================================
cat19 = [
    ("Direct command", "send the report to the marketing team by end of day"),
    ("Software instruction", "click on settings then go to advanced and enable developer mode"),
    ("Delegation", "can you handle the code review while I work on the presentation"),
    ("Priority instruction", "focus on the critical bugs first then work on the feature requests"),
    ("Conditional instruction", "if the build passes deploy to staging but if it fails rollback immediately"),
    ("Multi-step", "download the latest version extract it to the project folder and run the setup script"),
    ("Reminder", "remind me to update the changelog before we release on Thursday"),
    ("Schedule", "lets schedule a sync for Monday morning at 10 AM to discuss the roadmap"),
]

# ============================================================
# CATEGORY 20: Difficult preservation cases
# ============================================================
cat20 = [
    ("Intentional like", "I like this approach better than the previous one"),
    ("Intentional right", "the answer is on the right side of the page"),
    ("Intentional so", "the ratio is so high that it crashes the server"),
    ("Intentional well", "the well was drilled about 200 feet deep"),
    ("Intentional mean", "what does this error message mean"),
    ("Intentional actually", "we actually need to keep this feature its used by 40 percent of our users"),
    ("Intentional okay", "click okay to confirm the deletion"),
    ("Intentional basically", "the algorithm is basically a modified binary search"),
    ("I mean meaning", "I mean the error not the warning thats a different issue"),
    ("Right as correct", "yeah thats right the config goes in the root directory"),
]

all_categories = [
    ("FILLER REMOVAL", cat1),
    ("PUNCTUATION & CAPS", cat2),
    ("FALSE STARTS", cat3),
    ("PROFESSIONAL", cat4),
    ("TECHNICAL", cat5),
    ("EMOTIONAL/CASUAL", cat6),
    ("QUESTIONS (must not answer)", cat7),
    ("EDGE CASES", cat8),
    ("REAL USER DICTATION", cat9),
    ("HALLUCINATION TRIGGERS", cat10),
    ("CONTENT PRESERVATION", cat11),
    ("MIXED FILLER + CONTENT", cat12),
    ("LONGER DICTATION", cat13),
    ("CONTRACTIONS & INFORMAL", cat14),
    ("NUMBERS, DATES, MEASUREMENTS", cat15),
    ("MULTI-SENTENCE COHERENCE", cat16),
    ("DOMAIN-SPECIFIC", cat17),
    ("WHISPER ARTIFACTS", cat18),
    ("COMMANDS & INSTRUCTIONS", cat19),
    ("DIFFICULT PRESERVATION", cat20),
]

total_tests = 0
total_passed = 0
total_guarded = 0
notable = []

for cat_name, tests in all_categories:
    print(f"=== {cat_name} ===")
    print()
    cat_passed = 0
    cat_guarded = 0
    for label, text in tests:
        raw, final, ms, guarded = run_test(text)
        total_tests += 1
        if guarded:
            total_guarded += 1
            cat_guarded += 1
            status = "GUARD"
        else:
            total_passed += 1
            cat_passed += 1
            status = "OK"

        print(f"[{status}] {label} ({ms}ms)")
        print(f"  IN:  {text[:120]}{'...' if len(text) > 120 else ''}")
        print(f"  OUT: {final[:120]}{'...' if len(final) > 120 else ''}")
        if guarded:
            print(f"  RAW: {raw[:100]}... (rejected)")
        print()

    print(f"  >> {cat_name}: {cat_passed}/{cat_passed + cat_guarded} passed")
    print()

print(f"=== SUMMARY: {total_passed} passed, {total_guarded} guarded, {total_tests} total ===")
print(f"=== PASS RATE: {total_passed/total_tests*100:.1f}% ===")
