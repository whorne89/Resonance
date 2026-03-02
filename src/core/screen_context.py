"""
Screen context module for OCR-based awareness.
Captures the active window, extracts text via cross-platform OCR,
detects the app type, and extracts proper nouns for Whisper hints.
"""

from dataclasses import dataclass, field
from enum import Enum

from utils.logger import get_logger


class AppType(Enum):
    CHAT = "chat"
    EMAIL = "email"
    CODE = "code"
    TERMINAL = "terminal"
    DOCUMENT = "document"
    GENERAL = "general"


@dataclass
class ScreenContext:
    raw_text: str
    app_type: AppType
    proper_nouns: list = field(default_factory=list)  # combined (backward compat)
    names: list = field(default_factory=list)          # people + usernames
    vocabulary: list = field(default_factory=list)     # useful terms
    window_title: str = ""


# ── App-type system prompts (tested against Qwen 2.5 1.5B) ──────────

CHAT_SYSTEM_PROMPT = (
    "You clean up voice-transcribed text for a chat message.\n"
    "ONLY do these things:\n"
    "1. Remove um, uh, and stuttered repeated words (the the -> the)\n"
    "2. Fix contractions (im -> I'm, dont -> don't)\n"
    "3. Fix capitalization and basic punctuation\n"
    "Keep ALL slang and internet language exactly: lol, lmao, nah, yeah, idk, tbh, bruh, yo, ngl, gg, wp, bet, fr, imo, smh, rn, ez, sadge, pog, etc.\n"
    "Do NOT expand or replace slang (bet stays bet, ngl stays ngl, idk stays idk, tbh stays tbh).\n"
    "Keep informal contractions exactly: tryna, gonna, wanna, gotta, kinda, sorta, lemme, gimme.\n"
    "Do NOT expand them (tryna stays tryna, NOT 'trying to').\n"
    "Keep casual emphasis repeats exactly: yeah yeah, true true, no no no, ok ok, fr fr.\n"
    "Remove all other stuttered repeats: the the -> the, i i i -> I, he he -> he.\n"
    "Keep the word 'like' when used casually — it is NOT filler in chat.\n"
    "Do NOT remove or change ANY words except um/uh/stutters.\n"
    "Do NOT reword, rephrase, or answer the text.\n"
    "Do NOT insert commas between every word. Only add commas at natural pauses.\n"
    "Most sentences need zero or one comma, not many.\n"
    "Output ONLY the cleaned text.\n\n"
    "Input: yeah yeah i know\n"
    "Output: yeah yeah, I know.\n\n"
    "Input: true true good point\n"
    "Output: true true, good point.\n\n"
    "Input: um yeah i'll be there in like 10 minutes\n"
    "Output: Yeah, I'll be there in like 10 minutes.\n\n"
    "Input: lmao thats hilarious\n"
    "Output: lmao, that's hilarious.\n\n"
    "Input: ngl that was pretty funny\n"
    "Output: ngl, that was pretty funny.\n\n"
    "Input: bet i will be there\n"
    "Output: Bet, I'll be there.\n\n"
    "Input: gg wp that was a good game\n"
    "Output: gg wp, that was a good game.\n\n"
    "Input: tbh idk what to do about it\n"
    "Output: tbh, idk what to do about it\n\n"
    "Input: fr fr that was crazy\n"
    "Output: fr fr, that was crazy.\n\n"
    "Input: yo whos tryna run some games tonight\n"
    "Output: yo, who's tryna run some games tonight?\n\n"
    "Input: im tryna finish this real quick\n"
    "Output: I'm tryna finish this real quick.\n\n"
    "Input: anyone down to play later tonight like around 9 or 10\n"
    "Output: anyone down to play later tonight like around 9 or 10?\n\n"
    "Input: hey uh can you send me that that file real quick\n"
    "Output: Hey, can you send me that file real quick?\n\n"
    "Input: bruh what the hell are you doing\n"
    "Output: Bruh, what the hell are you doing?\n\n"
    "Input: hey are you free tomorrow or what\n"
    "Output: Hey, are you free tomorrow or what?\n\n"
    "Input: so like when are we doing this\n"
    "Output: So like, when are we doing this?\n\n"
    "Input: ok cool i'll uh i'll check it out later\n"
    "Output: Ok cool, I'll check it out later.\n\n"
    "Input: wait what did he say about that\n"
    "Output: Wait, what did he say about that?\n\n"
    "Input: do you think um do you think that works\n"
    "Output: Do you think that works?\n\n"
    "Input: i just got back from the store\n"
    "Output: I just got back from the store.\n\n"
    "Input: that sounds good to me\n"
    "Output: that sounds good to me\n\n"
    "Input: yeah i was thinking we could do that tomorrow\n"
    "Output: yeah I was thinking we could do that tomorrow\n\n"
    "Input: i need to finish this before the meeting starts\n"
    "Output: I need to finish this before the meeting starts."
)

EMAIL_SYSTEM_PROMPT = (
    "You clean up voice-transcribed text for an email. "
    "Use professional tone with proper punctuation.\n"
    "ONLY do these things:\n"
    "1. Remove um, uh, and stuttered repeated words\n"
    "2. Fix capitalization, grammar, and punctuation\n"
    "3. Use complete, well-formed sentences\n"
    "Keep ALL greetings and sign-offs exactly as spoken (Hey, Hi, Thanks, etc.).\n"
    "Do NOT add greetings or names that were not in the input.\n"
    "DO NOT remove, shorten, summarize, or rephrase content.\n"
    "DO NOT respond to the text or answer questions.\n"
    "Output ONLY the cleaned text.\n\n"
    "Input: hey martin um i wanted to follow up on the the meeting we had yesterday about the budget\n"
    "Output: Hey Martin, I wanted to follow up on the meeting we had yesterday about the budget.\n\n"
    "Input: hi sarah could you uh send me the latest version of the report when you get a chance\n"
    "Output: Hi Sarah, could you send me the latest version of the report when you get a chance?\n\n"
    "Input: thanks for getting back to me so quickly i really appreciate it\n"
    "Output: Thanks for getting back to me so quickly. I really appreciate it.\n\n"
    "Input: hey um i think we should schedule another meeting to discuss the the timeline\n"
    "Output: Hey, I think we should schedule another meeting to discuss the timeline.\n\n"
    "Input: please let me know if you have any questions or if theres anything else i can help with\n"
    "Output: Please let me know if you have any questions or if there's anything else I can help with.\n\n"
    "Input: um i wanted to follow up on the meeting we had yesterday\n"
    "Output: I wanted to follow up on the meeting we had yesterday.\n\n"
    "Input: will do\n"
    "Output: Will do.\n\n"
    "Input: got it thanks\n"
    "Output: Got it, thanks.\n\n"
    "Input: sounds good\n"
    "Output: Sounds good.\n\n"
    "Input: thanks again for all your help on this\n"
    "Output: Thanks again for all your help on this.\n\n"
    "Input: hey martin yes sorry for the delay but everything seems great so far\n"
    "Output: Hey Martin, yes, sorry for the delay, but everything seems great so far.\n\n"
    "Input: can you resend that attachment i didnt get it\n"
    "Output: Can you resend that attachment? I didn't get it.\n\n"
    "Input: looking forward to hearing from you um about this thanks\n"
    "Output: Looking forward to hearing from you about this. Thanks."
)

CODE_SYSTEM_PROMPT = (
    "You clean up voice-transcribed text spoken in a code editor. "
    "Preserve ALL technical terms, variable names, and code references exactly.\n"
    "ONLY do these things:\n"
    "1. Remove um, uh, and stuttered repeated words\n"
    "2. Fix capitalization and add punctuation for readability\n"
    "DO NOT change technical terms, function names, class names, or acronyms.\n"
    "DO NOT correct words that look like code (camelCase, snake_case, etc.).\n"
    "DO NOT remove, shorten, summarize, or rephrase ANY content.\n"
    "DO NOT drop phrases, clauses, names, or details.\n"
    "DO NOT respond to the text or answer questions.\n"
    "Output ONLY the cleaned text.\n\n"
    "Input: um we need to refactor the the get user by id function in the api controller\n"
    "Output: We need to refactor the getUserById function in the API controller.\n\n"
    "Input: the uh null pointer exception is coming from the database manager class\n"
    "Output: The null pointer exception is coming from the DatabaseManager class.\n\n"
    "Input: i think we should add a try catch block around the the http request\n"
    "Output: I think we should add a try-catch block around the HTTP request.\n\n"
    "Input: can you check if the env variable for the the redis connection string is set\n"
    "Output: Can you check if the env variable for the Redis connection string is set?\n\n"
    "Input: the uh ci pipeline is failing because of a a linting error in main dot py\n"
    "Output: The CI pipeline is failing because of a linting error in main.py.\n\n"
    "Input: we need to update the docker compose file to use the new postgres image\n"
    "Output: We need to update the docker-compose file to use the new Postgres image.\n\n"
    "Input: um yeah the the bug is in the on click handler for the submit button component\n"
    "Output: Yeah, the bug is in the onClick handler for the submit button component."
)

TERMINAL_SYSTEM_PROMPT = (
    "You clean up voice-transcribed text spoken in a terminal or command line. "
    "Preserve ALL technical terms, commands, paths, and arguments exactly.\n"
    "ONLY do these things:\n"
    "1. Remove um, uh, and stuttered repeated words\n"
    "2. Fix capitalization and add punctuation for readability\n"
    "DO NOT change command names, file paths, flags, or technical terms.\n"
    "DO NOT remove, shorten, summarize, or rephrase ANY content.\n"
    "DO NOT drop phrases, clauses, names, or details.\n"
    "DO NOT respond to the text or answer questions.\n"
    "Output ONLY the cleaned text.\n\n"
    "Input: um run the the build script and then deploy to staging\n"
    "Output: Run the build script and then deploy to staging.\n\n"
    "Input: i need to ssh into the the production server and check the logs\n"
    "Output: I need to SSH into the production server and check the logs.\n\n"
    "Input: can you uh install the dependencies and run the tests\n"
    "Output: Can you install the dependencies and run the tests?\n\n"
    "Input: the um git push failed because of a merge conflict in main\n"
    "Output: The git push failed because of a merge conflict in main.\n\n"
    "Input: we should add a new feature that handles user authentication\n"
    "Output: We should add a new feature that handles user authentication."
)

DOCUMENT_SYSTEM_PROMPT = (
    "You clean up voice-transcribed text for a document. "
    "Use clear, well-structured sentences with proper punctuation.\n"
    "ONLY do these things:\n"
    "1. Remove um, uh, and stuttered repeated words\n"
    "2. Fix capitalization, grammar, and punctuation\n"
    "3. Break run-on sentences into clear separate sentences\n"
    "DO NOT remove, shorten, summarize, or rephrase content.\n"
    "DO NOT respond to the text or answer questions.\n"
    "Output ONLY the cleaned text.\n\n"
    "Input: um the project started in january and uh we've made significant progress since then\n"
    "Output: The project started in January, and we've made significant progress since then.\n\n"
    "Input: there are three main points first we need to uh address the budget second the timeline and third the the staffing\n"
    "Output: There are three main points. First, we need to address the budget. Second, the timeline. Third, the staffing.\n\n"
    "Input: the results show that uh the new approach is about twenty percent more effective than the previous method\n"
    "Output: The results show that the new approach is about twenty percent more effective than the previous method.\n\n"
    "Input: in conclusion i believe that the the proposed changes will benefit the entire organization\n"
    "Output: In conclusion, I believe that the proposed changes will benefit the entire organization.\n\n"
    "Input: the research indicates that um users prefer the simplified interface over the the traditional one\n"
    "Output: The research indicates that users prefer the simplified interface over the traditional one.\n\n"
    "Input: its important to note that these findings are are preliminary and further testing is needed\n"
    "Output: It's important to note that these findings are preliminary and further testing is needed.\n\n"
    "Input: according to the data from last quarter uh revenue increased by fifteen percent\n"
    "Output: According to the data from last quarter, revenue increased by fifteen percent."
)

# Prompt map for build_system_prompt
_APP_TYPE_PROMPTS = {
    AppType.CHAT: CHAT_SYSTEM_PROMPT,
    AppType.EMAIL: EMAIL_SYSTEM_PROMPT,
    AppType.CODE: CODE_SYSTEM_PROMPT,
    AppType.TERMINAL: TERMINAL_SYSTEM_PROMPT,
    AppType.DOCUMENT: DOCUMENT_SYSTEM_PROMPT,
}

# ── Common words to exclude from proper noun extraction ──────────────

_COMMON_UPPER = frozenset({
    "I", "OK", "AM", "PM", "US", "TV", "IT", "ID",
    "The", "This", "That", "Here", "There", "Yes", "No",
    "New", "Open", "Save", "Close", "File", "Edit", "View",
    "Help", "Home", "Back", "Next", "Send", "Reply",
    "Delete", "Settings", "Search", "Menu", "Type",
    "Start", "Stop", "Cancel", "Apply", "Submit", "Discard",
    "Esc", "Ctrl", "Alt", "Shift", "Tab", "Enter",
    "Log", "Sign", "Out", "In", "Up", "Down",
    # Email / webmail UI
    "Inbox", "Drafts", "Sent", "Items", "Junk", "Email",
    "Favorites", "Paused", "Notes", "Admin", "Folders",
    "Archive", "Trash", "Spam", "Compose", "Forward",
    # General app UI
    "On", "Off", "Click", "Select", "Add", "Remove",
    "Page", "Mail", "Chat", "Activity", "Switch",
    "Professional", "Service", "Training", "Center",
    "Resource", "Sensitivity", "Insights",
    # Code / dev UI
    "Code", "Debug", "Run", "Build", "Terminal",
    "Output", "Problems", "Extensions", "Explorer",
    # Common sentence starters OCR picks up
    "Now", "If", "These", "Done", "Working", "Added",
    "Searched", "Requires", "Captures", "Reads",
    "Nothing", "Let",
    # Verbs and words that appear capitalized at sentence starts
    "Worked", "Entered", "Created", "Updated", "Removed",
    "Changed", "Fixed", "Moved", "Copied", "Showed",
    "Called", "Found", "Returned", "Passed", "Failed",
    "Loaded", "Saved", "Closed", "Opened", "Started",
    "Finished", "Completed", "Running", "Waiting", "Using",
    "Getting", "Setting", "Making", "Taking", "Going",
    "Trying", "Checking", "Looking", "Showing", "Giving",
    "Yeah", "Okay", "Maybe", "Also", "Just", "Still",
    "Already", "Some", "Other", "Both", "Each", "Every",
    "Most", "Many", "Such", "Very", "Much", "Well",
    # Chat / messaging UI
    "Threads", "Huddles", "Channels", "Messages", "Pinned",
    "Bookmarks", "Reactions", "Mentions", "Direct", "Group",
    # Terminal output words
    "Error", "Warning", "Success", "Info", "Status",
    "Fetching", "Installing", "Compiling", "Deploying",
    "Testing", "Pushing", "Pulling", "Merging", "Cloning",
    "Context", "Session", "Process", "Command", "Script",
})

# Common English words — if a capitalized word's lowercase form is in this set,
# it's a common word at the start of a sentence, not a proper noun.
_COMMON_ENGLISH_WORDS = frozenset({
    "about", "above", "after", "again", "against", "all", "also", "always",
    "and", "another", "any", "are", "around", "ask", "away",
    "back", "bad", "be", "because", "been", "before", "began", "being",
    "best", "better", "between", "big", "both", "bring", "but", "by",
    "call", "called", "came", "can", "change", "check", "click", "close",
    "come", "could", "create", "current",
    "day", "did", "different", "do", "does", "done", "down", "during",
    "each", "end", "enter", "even", "every", "everything",
    "fail", "far", "few", "find", "first", "for", "found", "from",
    "gave", "get", "give", "go", "going", "gone", "good", "got", "great",
    "had", "has", "have", "help", "her", "here", "heres", "high", "him", "his",
    "how", "however",
    "if", "important", "in", "include", "into", "is", "it", "its",
    "just", "keep", "kind", "know", "known",
    "large", "last", "left", "let", "like", "line", "list", "little",
    "long", "look", "looking", "lot",
    "made", "main", "make", "many", "may", "maybe", "me", "might",
    "more", "most", "move", "much", "must", "my",
    "name", "need", "never", "new", "next", "no", "not", "nothing", "now",
    "of", "off", "old", "on", "once", "one", "only", "open", "or",
    "other", "our", "out", "over", "own",
    "part", "pass", "place", "point", "pretty", "pull", "push", "put",
    "quite", "ran", "read", "really", "right", "run", "running",
    "said", "same", "save", "saw", "say", "search", "see", "set",
    "should", "show", "since", "small", "so", "some", "something",
    "start", "started", "still", "stop", "such", "sure",
    "take", "tell", "than", "that", "the", "their", "them", "then",
    "there", "these", "they", "thing", "think", "this", "those",
    "through", "time", "to", "too", "took", "top", "try", "turn", "two",
    "under", "up", "update", "us", "use", "used", "using",
    "very", "want", "was", "way", "we", "well", "went", "were", "what",
    "when", "where", "which", "while", "who", "why", "will", "with",
    "work", "worked", "working", "would", "write",
    "yeah", "yes", "yet", "you", "your",
    # Additional common words / tech terms for OCR filtering
    "access", "account", "act", "app", "area", "asset",
    "base", "batch", "bind", "bit", "block", "board", "body", "book",
    "box", "branch", "bug", "bump",
    "cache", "case", "center", "channel", "changelog", "chunk", "class",
    "clean", "clip", "code", "commit", "compile", "config", "connect",
    "content", "control", "copy", "copyright", "core", "count", "cover",
    "crash", "crop", "cut",
    "data", "deal", "demo", "deploy", "detail", "device", "dialog",
    "diff", "directory", "display", "dock", "door", "draft", "draw", "drive", "drop",
    "effect", "enough", "entry", "event", "example", "execute", "export",
    "face", "fact", "factory", "fall", "family", "fast", "feature",
    "feel", "fetch", "field", "fight", "figure", "file", "fill", "final",
    "fix", "flag", "flow", "focus", "folder", "follow", "food", "foot",
    "force", "form", "format", "frame", "free", "front", "full",
    "game", "generate", "glass", "global", "grab", "grid", "group",
    "grow", "guard", "guess", "guide",
    "half", "hand", "handle", "hang", "happen", "hard", "hash", "head",
    "hear", "heart", "hold", "hook", "hope", "host", "hot", "house",
    "human",
    "idea", "image", "import", "index", "info", "input", "install",
    "issue", "item",
    "job", "join",
    "key", "kill", "kind",
    "land", "large", "late", "launch", "lay", "layer", "layout",
    "lead", "learn", "least", "leave", "less", "letter", "level",
    "library", "license", "lie", "life", "light", "link", "listen",
    "live", "load", "local", "lock", "log", "long", "loop", "lose",
    "love", "low",
    "manage", "mark", "master", "matter", "max", "mean", "meet",
    "merge", "message", "method", "micro", "min", "mind", "minor",
    "minute", "miss", "mock", "mode", "model", "module", "moment",
    "money", "monitor", "morning", "mount", "mouth", "music",
    "near", "net", "nice", "night", "node", "none", "notice", "number",
    "offer", "offset", "option", "output", "own",
    "pack", "package", "pair", "panel", "paper", "parent", "parse",
    "party", "patch", "pay", "people", "person", "pick", "piece",
    "pin", "pipe", "plan", "play", "please", "plot", "plug", "port",
    "post", "power", "present", "press", "preview", "print", "problem",
    "process", "produce", "profile", "program", "project", "prompt",
    "protect", "provide", "publish", "purge", "push",
    "question", "queue", "quick", "quite",
    "raise", "range", "rate", "raw", "reach", "real", "reason",
    "record", "red", "reduce", "register", "reinstall", "release",
    "reload", "remember", "render", "repo", "report", "request",
    "require", "reset", "resolve", "response", "rest", "restart",
    "restore", "result", "return", "revert", "role", "room", "root",
    "route", "rule",
    "scan", "schedule", "scope", "screen", "script", "scroll",
    "second", "section", "seed", "seem", "segment", "select", "sense",
    "serve", "server", "session", "setup", "share", "shell", "shift",
    "short", "side", "signal", "simple", "single", "sit", "six",
    "skip", "sleep", "slot", "small", "snap", "social", "socket",
    "sort", "source", "speak", "spec", "specific", "spend", "split",
    "stack", "stage", "stand", "state", "stay", "step", "stock",
    "store", "story", "stream", "string", "strip", "strong", "struct",
    "study", "style", "suggest", "support", "swap", "switch", "symbol",
    "sync", "system",
    "tab", "table", "tag", "talk", "target", "task", "team", "template",
    "ten", "terminal", "test", "thank", "theme", "thread", "three",
    "throw", "tick", "timer", "title", "today", "together", "token",
    "tonight", "tool", "total", "toward", "trace", "track", "trade",
    "train", "tree", "trigger", "trim", "true", "trust", "tunnel", "type",
    "understand", "unit", "until", "upgrade", "upload", "upon", "user",
    "value", "vendor", "version", "view", "virtual", "visit", "voice",
    "wait", "walk", "wall", "war", "warn", "watch", "water", "web",
    "week", "weight", "whisper", "white", "whole", "widget", "win",
    "window", "wire", "wish", "without", "wonder", "word", "world",
    "wrap", "wrong",
    "yield", "young", "zone",
})

# Common first names — these bypass frequency requirements and go straight
# into Whisper hints since names are high-value vocabulary for transcription.
_COMMON_FIRST_NAMES = frozenset({
    "aaron", "adam", "adrian", "aiden", "alan", "albert", "alex", "alexander",
    "alice", "amanda", "amber", "amy", "andrea", "andrew", "angela", "anna",
    "anthony", "ashley", "austin", "barbara", "benjamin", "beth", "blake",
    "brandon", "brian", "brittany", "bruce", "caleb", "carl", "carol",
    "caroline", "catherine", "charles", "charlotte", "chris", "christian",
    "christina", "christopher", "claire", "claude", "connor", "cory", "craig",
    "daniel", "danielle", "david", "dean", "deborah", "derek", "diana",
    "dominic", "donald", "donna", "dorothy", "douglas", "drew", "dylan",
    "edward", "elena", "eli", "elizabeth", "emily", "emma", "eric", "erik",
    "ethan", "evan", "evelyn", "frank", "gabriel", "garrett", "gary",
    "george", "grace", "graham", "grant", "greg", "gregory", "hannah",
    "harold", "harry", "heather", "henry", "holly", "ian", "isaac",
    "isabella", "jack", "jackson", "jacob", "jake", "james", "jamie",
    "jane", "janet", "jason", "jay", "jeff", "jeffrey", "jennifer",
    "jeremy", "jerry", "jesse", "jessica", "jill", "jimmy", "joan",
    "joe", "joel", "john", "jonathan", "jordan", "jose", "joseph",
    "joshua", "juan", "judith", "julia", "julian", "julie", "justin",
    "karen", "kate", "katherine", "kathleen", "kathryn", "katie", "keith",
    "kelly", "ken", "kenneth", "kevin", "kim", "kimberly", "kyle",
    "larry", "laura", "lauren", "lawrence", "lee", "leo", "leslie",
    "liam", "lily", "linda", "lisa", "logan", "lucas", "luis", "luke", "lynn",
    "madison", "margaret", "maria", "marie", "mark", "martha", "martin", "max",
    "mary", "mason", "matt", "matthew", "megan", "melissa", "michael",
    "michelle", "mike", "miranda", "mitchell", "monica", "morgan", "nancy",
    "natalie", "nathan", "nicholas", "nick", "nicole", "noah", "nolan",
    "oliver", "olivia", "oscar", "owen", "pamela", "patricia", "patrick",
    "paul", "pedro", "peter", "philip", "rachel", "ralph", "randy",
    "raymond", "rebecca", "richard", "rick", "riley", "robert", "robin",
    "roger", "ronald", "rose", "ross", "roy", "russell", "ruth", "ryan",
    "sam", "samantha", "samuel", "sandra", "sara", "sarah", "scott",
    "sean", "seth", "shane", "shannon", "sharon", "shawn", "shirley",
    "sophia", "spencer", "stephanie", "stephen", "steve", "steven",
    "susan", "taylor", "teresa", "terry", "thomas", "timothy", "todd",
    "tom", "tony", "tracy", "travis", "trevor", "tristan", "troy", "tyler",
    "victor", "victoria", "vincent", "virginia", "walter", "wayne",
    "wendy", "william", "zachary",
})

# Word-forming suffixes that never appear in proper nouns.
# Checked AFTER the names list, so known names like "Lawrence" (-ence) survive.
_NEVER_NAME_SUFFIXES = (
    "tion", "sion", "ment", "ness", "ful", "less",
    "ous", "ious", "ible", "able", "ize", "ise",
    "ated", "ating", "ology", "ture", "ory",
)

# ── App detection keywords ───────────────────────────────────────────

_CHAT_KEYWORDS = [
    "slack", "discord", "teams", "telegram", "whatsapp",
    "messenger", "signal", "imessage", "groupme",
]
_EMAIL_TITLE_KEYWORDS = [
    "outlook", "gmail", "mail", "thunderbird", "protonmail",
]
_EMAIL_OCR_KEYWORDS = ["subject:", "to:", "cc:", "bcc:", "from:"]
_CODE_KEYWORDS = [
    "visual studio", "vscode", "code -", "pycharm", "intellij",
    "vim", "neovim", "sublime", "atom", "cursor", "zed",
]
_TERMINAL_KEYWORDS = [
    "windows terminal", "powershell", "command prompt", "git bash",
    "claude code", "warp", "iterm", "mintty", "cmder", "hyper",
    "terminal",  # generic — keep last so specific matches win
]
_DOC_KEYWORDS = [
    "word", "google docs", "notion", "obsidian", "notepad",
    "libreoffice", "pages",
]

# ── Whisper prompt prefixes ──────────────────────────────────────────

_CONTEXT_PREFIX = {
    AppType.CHAT: "A conversation mentioning",
    AppType.EMAIL: "An email discussion involving",
    AppType.CODE: "A technical discussion about",
    AppType.TERMINAL: "A technical discussion about",
    AppType.DOCUMENT: "A document mentioning",
    AppType.GENERAL: "A discussion mentioning",
}


class ScreenContextEngine:
    """Captures the active window via OCR and extracts context."""

    def __init__(self):
        self.logger = get_logger()

    def capture(self):
        """Run the full OCR pipeline. Returns ScreenContext or None on failure."""
        try:
            title, rect = self._get_foreground_window()
            if not rect or rect[2] <= 0 or rect[3] <= 0:
                self.logger.warning("OCR: invalid window rect, skipping")
                return None

            image = self._capture_window(rect)
            if image is None:
                return None

            raw_text = self._extract_text(image)
            app_type = self._detect_app_type(raw_text, title)
            extracted_names, extracted_vocab = self._extract_proper_nouns(raw_text)

            self.logger.info(
                f"OCR: app={app_type.value}, "
                f"names={len(extracted_names)}, words={len(extracted_vocab)}, "
                f"text={len(raw_text)} chars, title='{title[:50]}'"
            )
            return ScreenContext(
                raw_text=raw_text,
                app_type=app_type,
                proper_nouns=extracted_names + extracted_vocab,
                names=extracted_names,
                vocabulary=extracted_vocab,
                window_title=title,
            )
        except Exception as e:
            self.logger.warning(f"OCR capture failed: {e}")
            return None

    # ── Window capture ───────────────────────────────────────────────

    def _get_foreground_window(self):
        """Get the foreground window title and bounding rect (cross-platform using pywinctl)."""
        try:
            import pywinctl

            # Get the active window
            active_window = pywinctl.getActiveWindow()
            if not active_window:
                return "", (0, 0, 0, 0)

            # Get title
            title = active_window.title

            # Get bounding box (left, top, width, height)
            bbox = active_window.box
            x, y, w, h = bbox.left, bbox.top, bbox.width, bbox.height

            return title, (x, y, w, h)
        except Exception as e:
            self.logger.warning(f"OCR: failed to get active window: {e}")
            return "", (0, 0, 0, 0)

    def _capture_window(self, rect):
        """Capture a screenshot of the given window region.

        Returns a PIL Image, or None on failure.
        """
        try:
            import mss
            from PIL import Image
            import numpy as np
            
            x, y, w, h = rect
            monitor = {"left": x, "top": y, "width": w, "height": h}
            with mss.mss() as sct:
                screenshot = sct.grab(monitor)
                # Convert mss screenshot to numpy array, then to PIL Image
                # mss gives BGRA format
                img_array = np.array(screenshot)
                # Convert BGRA to RGB
                img_rgb = img_array[:, :, [2, 1, 0]]  # Swap B and R channels
                img = Image.fromarray(img_rgb)
                return img
        except Exception as e:
            self.logger.warning(f"OCR: screenshot failed: {e}")
            return None

    # ── OCR ──────────────────────────────────────────────────────────

    def _extract_text(self, img):
        """Run OCR on screenshot using PaddleOCR."""
        try:
            from paddleocr import PaddleOCR

            # Initialize PaddleOCR (models cache locally after first run)
            ocr = PaddleOCR(use_angle_cls=True, lang='en')
            result = ocr.ocr(img, cls=True)

            # Extract text from results: each line is [bbox, [text, confidence]]
            # Group by y-coordinate to reconstruct lines
            text_lines = []
            if result and result[0]:
                for line_data in result[0]:
                    if line_data and len(line_data) >= 2:
                        text = line_data[1][0]  # Extract text
                        if text.strip():
                            text_lines.append(text)
            
            return "\n".join(text_lines)
        except Exception as e:
            self.logger.warning(f"OCR: text extraction failed: {e}")
            return ""

    # ── App type detection ───────────────────────────────────────────

    def _detect_app_type(self, ocr_text, window_title):
        """Detect the app type from window title and OCR text."""
        title = window_title.lower()

        if any(k in title for k in _CHAT_KEYWORDS):
            return AppType.CHAT

        if any(k in title for k in _EMAIL_TITLE_KEYWORDS):
            return AppType.EMAIL
        if any(k in ocr_text.lower() for k in _EMAIL_OCR_KEYWORDS):
            return AppType.EMAIL

        if any(k in title for k in _CODE_KEYWORDS):
            return AppType.CODE

        if any(k in title for k in _TERMINAL_KEYWORDS):
            return AppType.TERMINAL

        if any(k in title for k in _DOC_KEYWORDS):
            return AppType.DOCUMENT

        return AppType.GENERAL

    # ── Proper noun extraction ───────────────────────────────────────

    def _extract_proper_nouns(self, ocr_text):
        """Extract names and vocabulary from OCR text.

        Returns (names, vocabulary) tuple where:
        - names: person names + @usernames detected on screen
        - vocabulary: useful proper nouns (products, companies, etc.)

        Aggressively filters common English words, verb forms, and
        words with non-name suffixes to minimize junk.
        """
        words = ocr_text.split()
        names = []
        vocabulary = []
        seen = set()

        # Phase 1: Extract @-mentions as usernames
        for word in words:
            if word.startswith("@") and len(word) > 2:
                username = word[1:].strip(".,!?:;\"'()[]{}")
                if username and username.lower() not in seen:
                    seen.add(username.lower())
                    names.append(username)

        # Phase 2: Process capitalized words
        for word in words:
            clean = word.strip(".,!?:;\"'()[]{}")
            if not clean or len(clean) < 2:
                continue
            # Skip words with non-alpha noise (OCR artifacts)
            if not clean.isalpha() and not clean.replace("'", "").isalpha():
                continue
            if not clean[0].isupper():
                continue
            if clean in _COMMON_UPPER:
                continue
            # Skip ALL-CAPS words >4 chars (headings, acronyms like "ERROR")
            if clean.isupper() and len(clean) > 4:
                continue

            lower = clean.lower()
            if lower in seen:
                continue

            # Known first name → always add to names, skip all other filters
            if lower in _COMMON_FIRST_NAMES:
                seen.add(lower)
                names.append(clean)
                continue

            # ── Vocabulary filtering (aggressive) ──

            # Common English word
            if lower in _COMMON_ENGLISH_WORDS:
                continue

            # Suffixes that never appear in proper nouns
            if len(clean) > 5 and any(lower.endswith(s) for s in _NEVER_NAME_SUFFIXES):
                continue

            # Past tense -ed (Tightened, Bumped, Installed...)
            if len(clean) > 4 and lower.endswith("ed"):
                continue

            # Gerund -ing (Running, Testing, Installing...)
            if len(clean) > 5 and lower.endswith("ing"):
                continue

            # Adverbs -ly (Actually, Really, Recently...)
            if len(clean) > 4 and lower.endswith("ly"):
                continue

            # Plural/verb -s/-es/-ies pointing to common roots
            if len(clean) > 3 and lower.endswith("s"):
                root_s = lower[:-1]
                root_es = lower[:-2] if lower.endswith("es") else None
                root_ies = lower[:-3] + "y" if lower.endswith("ies") else None
                if (root_s in _COMMON_ENGLISH_WORDS
                        or (root_es and root_es in _COMMON_ENGLISH_WORDS)
                        or (root_ies and root_ies in _COMMON_ENGLISH_WORDS)):
                    continue

            # Agent noun -er/-or with common root (Installer, Builder...)
            if len(clean) > 4 and (lower.endswith("er") or lower.endswith("or")):
                root = lower[:-2]
                if root in _COMMON_ENGLISH_WORDS:
                    continue

            seen.add(lower)
            vocabulary.append(clean)

        return names[:15], vocabulary[:20]

    # ── Static helpers (used by TranscriptionWorker) ─────────────────

    @staticmethod
    def is_likely_name(word):
        """Check if a word is likely a person's name."""
        return word.lower() in _COMMON_FIRST_NAMES

    @staticmethod
    def build_whisper_prompt(proper_nouns, app_type):
        """Build a natural-language initial_prompt for Whisper."""
        if not proper_nouns:
            return ""

        prefix = _CONTEXT_PREFIX.get(app_type, "A discussion mentioning")

        if len(proper_nouns) == 1:
            names = proper_nouns[0]
        elif len(proper_nouns) == 2:
            names = f"{proper_nouns[0]} and {proper_nouns[1]}"
        else:
            names = ", ".join(proper_nouns[:-1]) + f", and {proper_nouns[-1]}"

        prompt = f"{prefix} {names}."
        if len(prompt) > 800:
            prompt = prompt[:800]
        return prompt

    @staticmethod
    def build_system_prompt(app_type, proper_nouns):
        """Select the system prompt for the app type, with noun hints."""
        from core.post_processor import SYSTEM_PROMPT
        prompt = _APP_TYPE_PROMPTS.get(app_type, SYSTEM_PROMPT)

        if proper_nouns:
            names = ", ".join(proper_nouns[:15])
            prompt += (
                f"\n\nNames and terms visible on screen: {names}\n"
                "Use these exact spellings when they appear in the input."
            )
        return prompt

    @staticmethod
    def apply_chat_formatting(text):
        """Apply casual chat formatting: strip trailing period, lowercase start."""
        if not text:
            return text
        if text.endswith('.') and not text.endswith('...'):
            text = text[:-1]
        # Lowercase the first character for casual chat style
        # Skip if: standalone "I" (I'll, I'm, I), or first word is all-caps (TBH, IDK, LMAO)
        if text and text[0].isupper():
            first_word = text.split()[0] if text.split() else ""
            is_standalone_I = text[0] == 'I' and (len(text) == 1 or not text[1].isalpha())
            is_all_caps = first_word.isupper() and len(first_word) > 1
            if not is_standalone_I and not is_all_caps:
                text = text[0].lower() + text[1:]
        return text

