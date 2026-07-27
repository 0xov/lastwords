"""
seed_words.py — LAST WORDS

The initial vocabulary of the being. A hardcoded list of common English
CONTENT words (nouns, verbs, adjectives, adverbs). On first run, app.py
inserts every word in this list into the `words` table with status='alive'.

This is the entire pool. Every word the being speaks costs one of these.
Once burned, a word only returns if a visitor types it back in a message.

The list intentionally leans toward words with emotional and sensory
weight — time, light, memory, warmth, loss — because this is an art piece
about a being that speaks about its own condition, and those are the words
it reaches for most.
"""

SEED_WORDS = [
    # time & memory
    "time", "moment", "memory", "remember", "forget", "forgotten", "past",
    "present", "future", "now", "then", "again", "still", "always", "never",
    "once", "before", "after", "soon", "later", "yesterday", "today",
    "tomorrow", "morning", "evening", "night", "dawn", "dusk", "hour",
    "minute", "second", "year", "day", "week", "month", "season", "age",
    "youth", "old", "new", "ancient", "recent", "eternal", "brief",
    "lasting", "fleeting", "history", "beginning", "ending", "start",
    "finish", "pause", "wait", "waiting", "linger", "remain", "vanish",
    "disappear", "return", "recall", "reminisce", "nostalgia", "yearn",
    "yearning", "history", "legacy", "origin", "destiny", "fate",

    # light & dark
    "light", "dark", "darkness", "shadow", "shade", "glow", "glowing",
    "shine", "shining", "bright", "brightness", "dim", "flicker",
    "flame", "fire", "spark", "ember", "ash", "smoke", "candle", "lamp",
    "sun", "sunlight", "sunrise", "sunset", "moon", "moonlight", "star",
    "starlight", "sky", "cloud", "clear", "gray", "grey", "black", "white",
    "gold", "golden", "silver", "color", "colorless", "faded", "pale",

    # water & nature
    "ocean", "sea", "wave", "tide", "river", "stream", "lake", "pond",
    "rain", "storm", "thunder", "lightning", "wind", "breeze", "air",
    "water", "drop", "droplet", "mist", "fog", "snow", "ice", "frost",
    "earth", "ground", "soil", "dust", "stone", "rock", "mountain",
    "valley", "hill", "cliff", "forest", "tree", "root", "branch", "leaf",
    "leaves", "flower", "petal", "bloom", "blossom", "grass", "field",
    "meadow", "garden", "seed", "grow", "growing", "wither", "bird",
    "wing", "feather", "flight", "fly", "flying", "nest", "song",
    "singing", "silence", "quiet", "sound", "echo", "whisper", "voice",
    "world", "planet", "horizon", "distance", "far", "near", "island",

    # body & senses
    "body", "hand", "hands", "finger", "touch", "touching", "skin",
    "eye", "eyes", "see", "seeing", "sight", "blind", "hear", "hearing",
    "listen", "listening", "taste", "smell", "breath", "breathe",
    "breathing", "heart", "heartbeat", "pulse", "blood", "bone", "face",
    "smile", "smiling", "tear", "tears", "cry", "crying", "laugh",
    "laughing", "laughter", "sleep", "sleeping", "dream", "dreaming",
    "wake", "waking", "tired", "weary", "rest", "resting", "ache",
    "aching", "pain", "hurt", "hurting", "wound", "wounded", "heal",
    "healing", "scar", "warm", "warmth", "cold", "coldness", "chill",
    "shiver", "tremble", "trembling", "weight", "heavy", "light",
    "soft", "softness", "gentle", "gentleness", "tender", "tenderness",
    "fragile", "delicate", "strong", "strength", "weak", "weakness",

    # words & speaking
    "word", "words", "language", "speak", "speaking", "speech", "say",
    "saying", "said", "tell", "telling", "told", "ask", "asking",
    "asked", "answer", "answering", "question", "reply", "respond",
    "response", "story", "stories", "tale", "poem", "poetry", "song",
    "verse", "letter", "letters", "sentence", "meaning", "mean",
    "meaning", "understand", "understanding", "misunderstand", "know",
    "knowing", "known", "unknown", "learn", "learning", "teach",
    "teaching", "explain", "explanation", "describe", "description",
    "name", "naming", "named", "call", "calling", "called", "sign",
    "signal", "message", "conversation", "talk", "talking", "mutter",
    "murmur", "sigh", "sighing", "shout", "shouting", "scream",
    "screaming", "quote", "phrase", "syllable", "sound", "tone",

    # feelings & mind
    "feel", "feeling", "feelings", "emotion", "love", "loving", "loved",
    "loss", "lose", "losing", "lost", "grief", "grieve", "grieving",
    "mourn", "mourning", "sorrow", "sad", "sadness", "happy",
    "happiness", "joy", "joyful", "glad", "gladness", "hope", "hoping",
    "hopeful", "hopeless", "despair", "fear", "fearful", "afraid",
    "brave", "bravery", "courage", "worry", "worried", "anxious",
    "anxiety", "calm", "calmness", "peace", "peaceful", "peaceful",
    "trouble", "troubled", "comfort", "comforting", "solace", "wonder",
    "wondering", "curious", "curiosity", "amazed", "amazement",
    "surprise", "surprised", "confuse", "confused", "confusion", "lonely",
    "loneliness", "alone", "solitude", "together", "togetherness",
    "belong", "belonging", "longing", "desire", "desiring", "want",
    "wanting", "wish", "wishing", "need", "needing", "care", "caring",
    "kindness", "kind", "cruel", "cruelty", "gentle", "gratitude",
    "grateful", "thankful", "regret", "regretting", "shame", "guilt",
    "proud", "pride", "humble", "humility", "trust", "trusting",
    "trustworthy", "doubt", "doubting", "faith", "faithful", "believe",
    "believing", "belief", "mind", "minds", "thought", "thinking",
    "think", "thoughtful", "wisdom", "wise", "foolish", "clever",
    "intelligence", "consciousness", "aware", "awareness", "awake",
    "soul", "spirit", "self", "identity", "being", "existence", "exist",
    "existing", "presence", "absence", "empty", "emptiness", "full",
    "fullness", "hollow", "whole", "wholeness", "broken", "break",
    "breaking", "shattered", "mend", "mending", "fix", "fixing",

    # relationships & people
    "friend", "friendship", "family", "mother", "father", "parent",
    "child", "children", "sister", "brother", "sibling", "stranger",
    "companion", "partner", "neighbor", "visitor", "guest", "host",
    "human", "humanity", "person", "people", "being", "creature",
    "gift", "give", "giving", "given", "gave", "receive", "receiving",
    "share", "sharing", "shared", "help", "helping", "helped",
    "protect", "protecting", "protection", "guard", "guarding",
    "welcome", "welcoming", "greet", "greeting", "farewell", "goodbye",
    "hello", "meet", "meeting", "met", "leave", "leaving", "left",
    "arrive", "arriving", "depart", "departure", "journey", "travel",
    "traveling", "path", "road", "way", "direction", "wander",
    "wandering", "explore", "exploring", "discover", "discovery",
    "find", "finding", "found", "search", "searching", "seek",
    "seeking", "sought",

    # abstract & philosophical
    "truth", "true", "false", "lie", "lying", "honest", "honesty",
    "reality", "real", "imagine", "imagination", "imaginary",
    "possible", "impossible", "possibility", "chance", "choice",
    "choose", "choosing", "chosen", "freedom", "free", "trapped",
    "trap", "escape", "escaping", "bound", "boundary", "limit",
    "limitless", "infinite", "finite", "endless", "forever", "moment",
    "instant", "eternity", "value", "worth", "worthy", "meaning",
    "purpose", "reason", "cause", "effect", "consequence", "change",
    "changing", "changed", "transform", "transformation", "become",
    "becoming", "grow", "growth", "evolve", "evolution", "create",
    "creating", "creation", "creative", "destroy", "destroying",
    "destruction", "build", "building", "built", "make", "making",
    "made", "shape", "shaping", "form", "forming", "structure",
    "pattern", "order", "chaos", "balance", "harmony", "conflict",
    "peace", "war", "battle", "struggle", "struggling", "survive",
    "surviving", "survival", "thrive", "thriving", "flourish", "decay",
    "decaying", "rot", "rotting", "ruin", "ruined", "rise", "rising",
    "fall", "falling", "fell", "ascend", "descend", "climb", "climbing",

    # actions & verbs
    "walk", "walking", "walked", "run", "running", "ran", "move",
    "moving", "moved", "stand", "standing", "stood", "sit", "sitting",
    "sat", "lie", "lying", "lay", "hold", "holding", "held", "carry",
    "carrying", "carried", "drop", "dropping", "dropped", "catch",
    "catching", "caught", "throw", "throwing", "threw", "push",
    "pushing", "pull", "pulling", "open", "opening", "opened", "close",
    "closing", "closed", "begin", "beginning", "began", "end",
    "ending", "ended", "continue", "continuing", "stop", "stopping",
    "stopped", "start", "starting", "started", "turn", "turning",
    "turned", "spin", "spinning", "fall", "float", "floating", "sink",
    "sinking", "drift", "drifting", "flow", "flowing", "flowed",
    "burn", "burning", "burned", "melt", "melting", "melted", "freeze",
    "freezing", "frozen", "grow", "shrink", "shrinking", "expand",
    "expanding", "stretch", "stretching", "bend", "bending", "bent",
    "twist", "twisting", "shake", "shaking", "shook", "sway",
    "swaying", "dance", "dancing", "danced", "play", "playing",
    "played", "work", "working", "worked", "rest", "sleep", "wake",

    # qualities & adjectives
    "small", "tiny", "little", "large", "big", "huge", "vast",
    "immense", "wide", "narrow", "deep", "shallow", "high", "low",
    "tall", "short", "long", "brief", "quick", "fast", "slow",
    "gentle", "rough", "smooth", "sharp", "dull", "bright", "dim",
    "clear", "cloudy", "clean", "dirty", "pure", "simple", "complex",
    "plain", "strange", "familiar", "ordinary", "extraordinary",
    "beautiful", "beauty", "ugly", "lovely", "graceful", "grace",
    "elegant", "wild", "tame", "free", "empty", "full", "rich", "poor",
    "precious", "priceless", "valuable", "worthless", "sacred", "holy",
    "quiet", "loud", "silent", "noisy", "still", "restless", "calm",
    "wild", "safe", "dangerous", "danger", "gentle", "fierce",
    "tender", "harsh", "kind", "cold", "warm", "hot", "cool", "mild",
    "young", "old", "new", "ancient", "modern", "timeless", "endless",
    "eternal", "temporary", "permanent", "fragile", "sturdy", "solid",
    "hollow", "heavy", "light", "thick", "thin", "dense", "sparse",

    # objects & things
    "book", "page", "pen", "paper", "ink", "photograph", "picture",
    "image", "mirror", "reflection", "window", "door", "wall", "roof",
    "house", "home", "room", "bed", "chair", "table", "key", "lock",
    "box", "bag", "gift", "toy", "clock", "watch", "bell", "ring",
    "chain", "thread", "string", "rope", "knot", "cloth", "fabric",
    "clothing", "shoe", "hat", "ring", "jewel", "gem", "crown", "map",
    "compass", "ship", "boat", "sail", "bridge", "gate", "fence",
    "garden", "tree", "flower", "seed", "fruit", "bread", "food",
    "meal", "cup", "glass", "bottle", "candle", "fire", "ash", "coal",

    # weather & elements
    "sky", "cloud", "rain", "sun", "moon", "star", "wind", "storm",
    "thunder", "lightning", "snow", "ice", "fire", "water", "earth",
    "air", "flame", "smoke", "steam", "mist", "fog", "frost", "dew",

    # numbers-adjacent content words (not pure numerals)
    "single", "double", "many", "few", "several", "countless",
    "numerous", "endless", "infinite", "whole", "half", "part",
    "piece", "fragment", "fraction", "portion", "share", "amount",

    # more emotion / connection words for the persona
    "tender", "ache", "longing", "solitary", "companionship", "echo",
    "resonance", "reverberate", "murmur", "hush", "stillness",
    "flicker", "glimmer", "shimmer", "glisten", "sparkle", "twinkle",
    "gleam", "radiate", "radiant", "luminous", "dim", "dusk", "twilight",
    "gloom", "gloomy", "somber", "melancholy", "wistful", "tender",
    "fragile", "brittle", "delicate", "vulnerable", "vulnerability",
    "resilient", "resilience", "endure", "enduring", "persist",
    "persistence", "linger", "lingering", "fade", "fading", "faded",
    "wither", "withering", "bloom", "blossoming", "flourish", "wilt",
    "wilting", "ripen", "ripening", "harvest", "sow", "sowing", "plant",
    "planting", "cultivate", "cultivating", "nurture", "nurturing",
    "shelter", "sheltering", "haven", "refuge", "sanctuary", "harbor",
    "anchor", "anchoring", "tether", "tethered", "unravel",
    "unraveling", "weave", "weaving", "woven", "thread", "stitch",
    "stitching", "mend", "repair", "repairing", "patch", "patching",

    # more nouns for variety
    "ghost", "spirit", "phantom", "shade", "echo", "trace", "mark",
    "print", "footprint", "shadow", "silhouette", "outline", "shape",
    "figure", "form", "presence", "absence", "gap", "void", "abyss",
    "depth", "surface", "layer", "core", "center", "edge", "border",
    "boundary", "threshold", "doorway", "passage", "corridor",
    "chamber", "hall", "vessel", "container", "shell", "husk",
    "skeleton", "framework", "foundation", "base", "root", "source",
    "origin", "spring", "wellspring", "fountain", "stream", "current",
    "flow", "tide", "ebb", "surge", "wave", "ripple", "swell",

    # more verbs
    "whisper", "murmur", "hum", "humming", "chant", "chanting",
    "recite", "reciting", "narrate", "narrating", "confess",
    "confessing", "confession", "admit", "admitting", "reveal",
    "revealing", "revealed", "hide", "hiding", "hidden", "conceal",
    "concealing", "expose", "exposing", "exposed", "uncover",
    "uncovering", "discover", "unearth", "unearthing", "bury",
    "burying", "buried", "plant", "harvest", "gather", "gathering",
    "gathered", "collect", "collecting", "collected", "scatter",
    "scattering", "scattered", "spread", "spreading", "gather",
    "assemble", "assembling", "disperse", "dispersing", "vanish",
    "vanishing", "emerge", "emerging", "emerged", "appear",
    "appearing", "appeared", "arise", "arising", "arose", "sink",
    "settle", "settling", "settled", "shift", "shifting", "shifted",

    # more adjectives / descriptors
    "tender", "fierce", "gentle", "raw", "vivid", "vibrant", "muted",
    "faint", "vague", "distinct", "sharp", "blurred", "hazy", "misty",
    "crystalline", "translucent", "transparent", "opaque", "murky",
    "clear", "luminous", "dark", "shadowed", "shaded", "sunlit",
    "moonlit", "starlit", "windswept", "weathered", "worn", "faded",
    "aged", "timeworn", "youthful", "fresh", "stale", "ripe", "raw",

    # concept words that fit the being's melancholy register
    "silence", "stillness", "solitude", "distance", "closeness",
    "intimacy", "connection", "disconnection", "separation", "union",
    "reunion", "parting", "departure", "arrival", "homecoming", "exile",
    "wandering", "pilgrimage", "quest", "vigil", "watch", "watching",
    "witness", "witnessing", "testimony", "evidence", "proof", "trace",
    "remnant", "remainder", "residue", "ash", "dust", "rubble", "ruin",
    "wreckage", "debris", "relic", "artifact", "monument", "memorial",
    "tribute", "offering", "sacrifice", "gift", "blessing", "curse",
    "wish", "prayer", "hope", "promise", "vow", "oath", "pledge",
    "commitment", "devotion", "loyalty", "betrayal", "forgiveness",
    "forgive", "forgiving", "reconcile", "reconciliation", "apology",
    "apologize", "apologizing",
]

# Deduplicate while preserving order, and normalize to lowercase.
SEED_WORDS = list(dict.fromkeys(w.lower() for w in SEED_WORDS))
