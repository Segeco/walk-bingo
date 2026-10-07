"""
Walk Bingo: a printable nature bingo card for your next walk, made by a local AI.

Pick where you're going, how long for and who's coming. Google's open-weight
Gemma model (running on your own computer through Ollama) makes a 3x3 card of
things to spot, hear, smell and feel, suited to the season and today's weather.
Print it, put your phone away, and go outside.

Usage:
    ollama pull gemma3:4b
    python app.py
Then open http://127.0.0.1:8000
"""

import datetime
import json
import random
import re
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "gemma3:4b"
PORT = 8000

PLACES = {
    "park": "a town or city park",
    "woods": "woodland or a forest path",
    "countryside": "fields, footpaths and hedgerows in the countryside",
    "beach": "a beach or coastal path",
    "streets": "ordinary town or city streets",
    "garden": "a back garden",
    "canal": "a canal towpath or riverside",
}

COMPANY = {
    "solo": "on their own",
    "kids": "with young children (keep it fun, simple and safe)",
    "dog": "with their dog (include a square or two the dog helps with)",
    "friends": "with friends (include a square or two that needs teamwork)",
}

# Open-Meteo weather codes, simplified.
WEATHER_WORDS = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy with frost", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers",
    81: "heavy showers", 82: "violent showers", 95: "thunderstorms",
}

SYSTEM_PROMPT = """You make nature bingo cards for people going on a walk in the UK. The card is printed on paper, so the walk needs no phone at all.

Reply with JSON only, in exactly this shape:
{
  "title": "a short, cheerful title for this walk",
  "squares": [
    {"thing": "2 to 5 words", "hint": "one short sentence on where to look or how to tell"}
  ],
  "challenge": "one short 'slow down' challenge, e.g. stand still for one minute and count the different sounds",
  "tip": "one short practical tip based on the weather and sunset time"
}

Rules for the squares:
- Exactly 8 squares.
- Things that really are likely to be found in that place, in that season, in the UK.
- Mix the senses: mostly things to see, but at least one to hear, one to smell and one to touch or feel.
- Mix easy and hard: 3 easy, 3 medium, 2 that need a sharp eye.
- Never ask anyone to pick wild flowers, disturb nests or animals, eat anything, or go anywhere unsafe.
- Plain, friendly British English. No markdown."""

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Walk Bingo</title>
<style>
  :root { --ink: #1f2a1c; --leaf: #2f6b3a; --paper: #f7f4ea; --line: #c9c2ab; --muted: #5d6656; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: system-ui, sans-serif; background: var(--paper); color: var(--ink); line-height: 1.5; }
  main { max-width: 820px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }
  h1 { font-size: 2.4rem; margin: 0; color: var(--leaf); }
  .sub { margin: 0.2rem 0 1.5rem; color: var(--muted); font-size: 1.1rem; }
  form { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 1rem; align-items: end; }
  label { font-weight: 600; display: block; margin-bottom: 0.3rem; }
  select, input { width: 100%; font-size: 1rem; padding: 0.55rem; border: 2px solid var(--line); border-radius: 8px; background: white; }
  button { font-size: 1.1rem; padding: 0.7rem 1.4rem; border: none; border-radius: 10px; background: var(--leaf); color: white; cursor: pointer; }
  button:disabled { background: #8a9486; cursor: wait; }
  .actions { margin-top: 1rem; display: flex; gap: 0.7rem; flex-wrap: wrap; }
  .secondary { background: white; color: var(--leaf); border: 2px solid var(--leaf); }
  #status { margin-top: 1rem; color: var(--muted); }
  #card { display: none; margin-top: 2rem; background: white; border: 3px solid var(--ink); border-radius: 14px; padding: 1.4rem; }
  #card h2 { margin: 0; font-size: 1.8rem; }
  .meta { color: var(--muted); margin: 0.2rem 0 1rem; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); border: 2px solid var(--ink); }
  .sq { border: 1px solid var(--ink); padding: 0.7rem; min-height: 130px; cursor: pointer; position: relative; user-select: none; }
  .sq .thing { font-weight: 700; font-size: 1.1rem; }
  .sq .hint { font-size: 0.85rem; color: var(--muted); margin-top: 0.3rem; }
  .sq.free { background: #eaf2e3; display: flex; flex-direction: column; justify-content: center; text-align: center; }
  .sq.done::after { content: ""; position: absolute; inset: 12px; border: 4px solid var(--leaf); border-radius: 50%; opacity: 0.7; }
  .extra { margin-top: 1rem; display: grid; gap: 0.6rem; }
  .extra p { margin: 0; }
  .foot { margin-top: 1rem; font-size: 0.85rem; color: var(--muted); }
  @media (max-width: 560px) { .sq { min-height: 110px; padding: 0.45rem; } .sq .thing { font-size: 0.95rem; } .sq .hint { font-size: 0.75rem; } }
  @media print {
    body { background: white; }
    header, form, .actions, #status { display: none !important; }
    main { padding: 0; max-width: none; }
    #card { border: none; padding: 0; margin: 0; }
    .sq { min-height: 150px; }
  }
</style>
</head>
<body>
<main>
<header>
  <h1>Walk Bingo</h1>
  <p class="sub">Make a card, print it, leave your phone in your pocket, and go outside.</p>
</header>

<form id="f">
  <div><label for="place">Where are you going?</label>
    <select id="place">
      <option value="park">A park</option>
      <option value="woods">Woods</option>
      <option value="countryside">Countryside</option>
      <option value="beach">Beach or coast</option>
      <option value="canal">Canal or river</option>
      <option value="streets">Town streets</option>
      <option value="garden">The garden</option>
    </select></div>
  <div><label for="minutes">How long?</label>
    <select id="minutes">
      <option value="20">20 minutes</option>
      <option value="45" selected>45 minutes</option>
      <option value="90">An hour and a half</option>
      <option value="180">Half a day</option>
    </select></div>
  <div><label for="company">Who's coming?</label>
    <select id="company">
      <option value="solo">Just me</option>
      <option value="kids">With kids</option>
      <option value="dog">With the dog</option>
      <option value="friends">With friends</option>
    </select></div>
  <div><label for="town">Town (optional, for weather)</label>
    <input id="town" placeholder="e.g. Croydon"></div>
</form>
<div class="actions">
  <button id="go">Make my card</button>
  <button id="print" class="secondary" style="display:none">Print it</button>
</div>
<p id="status"></p>

<section id="card" aria-live="polite">
  <h2 id="title"></h2>
  <p class="meta" id="meta"></p>
  <div class="grid" id="grid"></div>
  <div class="extra">
    <p><strong>Slow down:</strong> <span id="challenge"></span></p>
    <p><strong>Before you go:</strong> <span id="tip"></span></p>
  </div>
  <p class="foot">Made by Walk Bingo on my own computer. Circle a square when you find it.</p>
</section>
</main>

<script>
const $ = id => document.getElementById(id);

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

$('go').onclick = async () => {
  const btn = $('go');
  btn.disabled = true; btn.textContent = 'Making your card...';
  $('status').textContent = 'Thinking. This can take a minute on a slower computer.';
  try {
    const res = await fetch('/card', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ place: $('place').value, minutes: $('minutes').value,
                             company: $('company').value, town: $('town').value.trim() })
    });
    const d = await res.json();
    if (d.error) throw new Error(d.error);
    render(d);
    $('status').textContent = '';
  } catch (e) {
    $('status').textContent = 'Sorry, something went wrong: ' + e.message;
  } finally {
    btn.disabled = false; btn.textContent = 'Make another card';
  }
};

$('print').onclick = () => window.print();

function render(d) {
  $('title').textContent = d.title;
  $('meta').textContent = d.meta;
  $('challenge').textContent = d.challenge;
  $('tip').textContent = d.tip;
  const cells = d.squares.map(s =>
    `<div class="sq"><div class="thing">${esc(s.thing)}</div><div class="hint">${esc(s.hint)}</div></div>`);
  cells.splice(4, 0, '<div class="sq free done"><div class="thing">FREE</div><div class="hint">You went outside!</div></div>');
  $('grid').innerHTML = cells.join('');
  $('grid').querySelectorAll('.sq:not(.free)').forEach(el => el.onclick = () => el.classList.toggle('done'));
  $('card').style.display = 'block';
  $('print').style.display = 'inline-block';
  $('card').scrollIntoView({behavior: 'smooth'});
}
</script>
</body>
</html>
"""


def season_for(date):
    m = date.month
    if m in (12, 1, 2):
        return "winter"
    if m in (3, 4, 5):
        return "spring"
    if m in (6, 7, 8):
        return "summer"
    return "autumn"


def get_json(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def weather_for(town):
    """Optional: today's weather and sunset from Open-Meteo (free, no key).
    Only the town name is sent. Returns None if offline or not found."""
    if not town:
        return None
    try:
        q = urllib.parse.urlencode({"name": town, "count": 1, "language": "en", "countryCode": "GB"})
        geo = get_json("https://geocoding-api.open-meteo.com/v1/search?" + q)
        if not geo.get("results"):
            return None
        place = geo["results"][0]
        q = urllib.parse.urlencode({
            "latitude": place["latitude"], "longitude": place["longitude"],
            "current": "temperature_2m,weather_code,wind_speed_10m",
            "daily": "sunset", "timezone": "auto", "forecast_days": 1,
        })
        wx = get_json("https://api.open-meteo.com/v1/forecast?" + q)
        cur = wx["current"]
        sunset = wx["daily"]["sunset"][0][-5:]
        words = WEATHER_WORDS.get(cur["weather_code"], "mixed weather")
        return {
            "place": place["name"],
            "text": f"{words}, {round(cur['temperature_2m'])}°C, wind {round(cur['wind_speed_10m'])} km/h, sunset at {sunset}",
        }
    except Exception:
        return None


def ask_model(system, user):
    payload = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        # A bit of randomness so "make another card" gives a different card.
        "options": {"temperature": 0.9, "seed": random.randint(1, 10**6)},
    }
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["message"]["content"]


def clean(text, limit):
    text = re.sub(r"[*#_`]+", "", str(text or "")).strip()
    return text[:limit]


def make_card(place, minutes, company, town):
    today = datetime.date.today()
    weather = weather_for(town)

    lines = [
        f"Today is {today.strftime('%A %d %B %Y')}, so it is {season_for(today)} in the UK.",
        f"The walk is in {PLACES.get(place, PLACES['park'])}.",
        f"It will last about {minutes} minutes.",
        f"They are going {COMPANY.get(company, COMPANY['solo'])}.",
    ]
    if weather:
        lines.append(f"The weather in {weather['place']} right now: {weather['text']}.")
    else:
        lines.append("The weather is unknown, so keep the tip general.")
    user = "\n".join(lines) + "\nMake the bingo card."

    data = json.loads(ask_model(SYSTEM_PROMPT, user))
    squares = [
        {"thing": clean(s.get("thing"), 40), "hint": clean(s.get("hint"), 120)}
        for s in data.get("squares", []) if isinstance(s, dict) and s.get("thing")
    ][:8]
    if len(squares) < 8:
        raise ValueError("The model made an incomplete card. Press the button again.")

    meta = f"{today.strftime('%A %d %B')} · {minutes} minutes"
    if weather:
        meta += f" · {weather['place']}: {weather['text']}"

    return {
        "title": clean(data.get("title"), 60) or "Walk Bingo",
        "meta": meta,
        "squares": squares,
        "challenge": clean(data.get("challenge"), 200) or "Stand still for one minute and count the different sounds you can hear.",
        "tip": clean(data.get("tip"), 200) or "Dress for the weather and tell someone where you're going.",
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json")

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        else:
            self._send(404, "Not found", "text/plain")

    def do_POST(self):
        if self.path != "/card":
            self._send(404, "Not found", "text/plain")
            return
        try:
            length = min(int(self.headers.get("Content-Length", 0)), 10_000)
            body = json.loads(self.rfile.read(length) or b"{}")
            minutes = int(body.get("minutes", 45))
            card = make_card(body.get("place", "park"), minutes,
                             body.get("company", "solo"), clean(body.get("town"), 60))
            self._json(200, card)
        except urllib.error.URLError:
            self._json(502, {"error": "Couldn't reach Ollama. Is it running? Try: ollama pull " + MODEL})
        except (ValueError, json.JSONDecodeError) as e:
            self._json(500, {"error": str(e) or "The model's answer didn't make sense. Press the button again."})
        except Exception as e:
            self._json(500, {"error": str(e)})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"Walk Bingo running at http://127.0.0.1:{PORT}  (model: {MODEL})")
    print("Press Ctrl+C to stop.")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
