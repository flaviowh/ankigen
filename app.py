from typing import Dict, List
import streamlit as st
from typing import List
import re
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO
import genanki
import hashlib

# ---- INSTRUCTIONS

INPUT_TIP = '''
📌 How to format your text

1️⃣ Direct or definition cards:
`question || answer` or `term : definition` on a single line.

2️⃣ Fill-in-the-blank (cloze) or classification cards:
Use square brackets to define a category or group.  
Then list the items below. 

Example 1 – inline items:
[Ash's Pokemons] contains Pikachu, Bulbasaur, Charmander
Pikachu
Bulbasaur
> Will blank Pikachu and Bulbasaur and create their own classification cards.  

Example 2 – items on separate lines:
[Ash's Pokemons] contains:
Pikachu,
Bulbasaur,
Charmander
> Will show the full paragraph with blanks and create a class card each.  

ℹ️Tips:
- Definitions are lines separated by colon ":" and create 2 cards (both ways)
- For fill-in cards, only the items listed below the bracket line will be turned into blanks.
- Tags can be added in the "Tags" field (separate multiple tags with commas).
'''

#-------------- Model
class CardType(Enum):
    FILL = "FILL"
    DIRECT = "SIMPLE"
    CLASSIFICATION = "CLASSIFICATION"

@dataclass
class Card:
    guid: str                     # deterministic SHA1 hash ID
    type: CardType                # card type
    question: str                 # card front
    answer: str                   # card back
    tags: List[str] = field(default_factory=list)
    

# ----------------------------- LOGIC -----------------------------

def gen_id_from_text(name: str) -> str:
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:16]

def is_direct_or_DIRECT_line(line: str) -> bool:
    # Detect lines with ":" or "||" as separators, but not at edges
    return bool(re.search(r'\S\s*(?:\|\||:)\s*\S', line))


def is_single_paragraph_fill(lines: List[str]) -> bool:
    if not lines or len(lines) < 2:
        return False
    first_line = lines[0].strip()
    return all(line.strip() in first_line for line in lines[1:] if line.strip())

def process_text( 
                text: str, 
                gen_fill: bool, 
                gen_class: bool,
                raw_tags: List[str]):
    lines = text.split("\n")
    tags = [t.replace(" ","_") for t in raw_tags]
    direct_lines = []
    cards = []
    other_lines = []
    for l in lines:
        if is_direct_or_DIRECT_line(l):
            direct_lines.append(l)
        else:
            other_lines.append(l)
            
    direct_cards = create_direct_cards(direct_lines, tags)
    cards.extend(direct_cards)
            
    other_cards = create_fill_and_classification_cards(other_lines, tags, gen_fill, gen_class)
    cards.extend(other_cards)
    
    return cards


def create_direct_cards(lines: List[str], tags: List[str]) -> List[Card]:
        cards = []
        if not lines:
            return cards
        
        for line in lines:
            parts = split_direct_line(lines)
            if not parts or len(parts) < 2:
                continue
            
            is_definition = not "||" in line
            front, back = parts
            cards.append(Card( guid="", type=CardType.DIRECT, 
                    question=f"Define {front}" if is_definition else front,
                    answer=line,  tags=tags)
        )   # also make a definition -> name card
            if is_definition:
                cards.append(Card( guid="", type=CardType.DIRECT, 
                    question=back, answer=front, tags=tags))
                
        return cards 


def split_direct_line(line: str) -> tuple[str, str] | None:
    for sep in ("||", ":"):
        if sep in line:
            front, back = map(str.strip, line.split(sep, 1))
            return front, back
    return None

    
def split_blocks(lines: List[str]) -> Dict[str, List[str]]:
    blocks = {}
    cur_block = []
    cur_struct = None

    for l in lines:
        l = l.strip()
        if not l:
            continue

        match =  re.search(r"\[(.+?)\]", l)
        if match:
            if cur_struct and cur_block:
                blocks[cur_struct] = cur_block

            cur_struct = match.group(1).strip()
            cur_block = [re.sub(r'[\[\]]', '', l)]
        else:
            cur_block.append(l)

    if cur_struct and cur_block:
        blocks[cur_struct] = cur_block

    return blocks

def create_fill_and_classification_cards(lines: List[str], tags: List[str], 
                    generate_fill: bool,
                    generate_class: bool) -> List[Card]:
    cards = []
    if not lines or not any([generate_fill , generate_class]):
        return cards

    blocks = split_blocks(lines)

    for struct_name, block in blocks.items():
        if not block:
            continue

        if generate_fill:
            fill_cards = create_fill_cards(block, tags)
            cards.extend(fill_cards)

        if generate_class:
            classification_cards = create_class_cards(block[1:], struct_name, tags)
            cards.extend(classification_cards)

    return cards

def create_fill_cards(lines_block: List[str], tags) -> List[Card]:
    cards = []
    #generate differently if the items are within the first line
    is_single_paragraph = is_single_paragraph_fill(lines_block)
    
    cloze_text = lines_block[0] if is_single_paragraph else "\n".join(lines_block) 
    for i, term in enumerate(lines_block[1:], 1):
        term_clean = " ".join(term.split())
        cloze_text = cloze_text.replace(term_clean, f"{{{{c{i}::{term_clean}}}}}", 1)
    cards.append(Card(
        guid="",
        type=CardType.FILL,
        question=cloze_text,
        answer=cloze_text,
        tags=tags
    ))
        
    return cards

def create_class_cards(items: List[str], struct_name: str, tags: List[str]) -> List[Card]:
    return [
        Card(
            guid="",
            type=CardType.CLASSIFICATION,
            question=item,
            answer=struct_name,
            tags=tags
        )
        for item in items
    ]       
        
        
# ----------------------------- PAGE CONFIG -----------------------------
st.set_page_config(
    page_title="AnkiGen",
    page_icon="📚",
    layout="centered",
)

# ----------------------------- HEADER -----------------------------
st.markdown("""
<div style='text-align: center; padding: 1.5rem;'>
    <h1 style='color: #2C7BE5;'>📚 AnkiGen</h1>
    <h3 style='color: #6C757D;'>Create Anki cards faster (no AI)</h3>
</div>
""", unsafe_allow_html=True)

# ----------------------------- FORM -----------------------------
with st.form("anki_form"):
    deck_name = st.text_input("Deck name", placeholder="My Deck", 
                            help="Reuse a name to update a previously created deck")
    text = st.text_area("Paste your formatted text here", 
                        height=250, 
                        placeholder= INPUT_TIP)
    
    tags = st.text_input("Tags", placeholder="tags, separated")

    st.text("Create from paragraphs:")
    col1, col2= st.columns(2, gap="small")
    with col1:
        rev = st.checkbox("Classifications")
    with col2:
        fill = st.checkbox("Blanks to fill")

    submitted = st.form_submit_button("📗Generate Anki Deck")


# ----------------------------- OUTPUT -----------------------------

def create_apkg(deck_name: str,cards : List[Card] ) -> BytesIO:
    """Generate an .apkg deck and return it as BytesIO"""
    deck_id = int(hashlib.sha1(deck_name.encode("utf-8")).hexdigest()[:8], 16)
    my_deck = genanki.Deck(deck_id, deck_name)

    # genanki models
    simple_model = genanki.Model(
            1761428899,
            'Basic Model',
            fields=[{'name': 'Front'}, {'name': 'Back'}],
            templates=[{
                'name': 'Card 1',
                'qfmt': '{{Front}}',
                'afmt': '{{FrontSide}}<hr id="answer">{{Back}}',
            }]
        )

    cloze_model = genanki.CLOZE_MODEL

    for c in cards:
        guid = gen_id_from_text(f"{c.question}||{deck_name}")
        if c.type == CardType.FILL:
            note = genanki.Note(
                model=cloze_model,
                fields=[c.question],
                tags=c.tags, 
                guid=guid
                )
        else:
            note = genanki.Note(
                model=simple_model,
                fields=[c.question, c.answer], 
                tags=c.tags, 
                guid=guid
                )
        my_deck.add_note(note)

    output = BytesIO()
    pkg = genanki.Package(my_deck)
    pkg.write_to_file(output)
    output.seek(0)
    return output


if submitted:
    if not text.strip():
        st.warning("Please enter the formatted text first.")
    else:
        cards = process_text(text,fill, rev, tags.split(","))
        num_cards = len(cards)

        if num_cards == 0:
            st.warning("No cards were created. Please check your input.")
        else:
            apkg_file = create_apkg(deck_name, cards)
            st.success(f"✅ Deck '{deck_name}' created with {num_cards} cards!")

            st.download_button(
                label="💾 Download .apkg",
                data=apkg_file,
                file_name=f"{deck_name}.apkg",
                mime="application/octet-stream",
            )


