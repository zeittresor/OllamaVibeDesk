from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_ROOT = get_app_root()
APP_DATA_DIR = APP_ROOT / "app_data"
CHATS_DIR = APP_DATA_DIR / "chats"
AUDIO_DIR = APP_DATA_DIR / "audio"
CACHE_DIR = APP_DATA_DIR / "cache"
EXPORTS_DIR = APP_DATA_DIR / "exports"
GENERATED_CODE_DIR = APP_DATA_DIR / "generated_code"
DEBUG_LOG_DIR = APP_DATA_DIR / "debug_logs"
SETTINGS_PROFILE_DIR = APP_DATA_DIR / "config_profiles"
TTS_DIR = APP_DATA_DIR / "tts"
LANG_DIR = APP_ROOT / "lang"
SAPI_LEXICON_PATH = TTS_DIR / "sapi_lexicon.json"
AUTO_ANSWER_PATH = APP_DATA_DIR / "auto_answer_phrases.json"
AUTO_ANSWER_QUESTION_REPLY_PATH = APP_DATA_DIR / "auto_answer_question_replies.json"
CONFIG_PATH = APP_DATA_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "ollama_base_url": "http://127.0.0.1:11434",
    "tts_backend": "windows_sapi",
    "tts_base_url": "http://127.0.0.1:8880/v1",
    "tts_voice": "",
    "tts_model": "tts-1-hd",
    "tts_format": "wav",
    "autoplay_tts": True,
    "auto_read_assistant_responses": True,
    "auto_read_user_inputs": True,
    "tts_lexicon_enabled": True,
    "windows_sapi_lexicon_enabled": True,
    "tts_user_voice": "",
    "windows_sapi_rate": 0,
    "windows_sapi_pitch": 3,
    "windows_sapi_volume": 100,
    "interface_language": "de",
    "theme": "Midnight",
    "last_model": "",
    "system_prompt": "",
    "auto_answer_enabled": True,
    "read_all_include_names": False,
    "user_display_name": "",
    "assistant_display_name": "",
    "strip_emojis_for_tts": True,
    "chat_max_tokens": 8192,
    "auto_answer_max_rounds": 0,
    "context_message_limit": 8,
    "auto_answer_short_answers": True,
    "auto_answer_eliza_share": 30,
    "auto_answer_phrase_repeat_lookback": 4,
    "rollover_carry_messages": 5,
    "auto_answer_short_instruction_overrides": {},
    "tts_voice_defaults_initialized": False,
    "debug_trace_enabled": False,
    "auto_thinking_for_code_requests": True,
    "auto_answer_use_question_replies_for_all": True,
    "allow_consecutive_auto_answer_dataset_reuse": False,
}


def ensure_default_sapi_lexicon() -> None:
    if SAPI_LEXICON_PATH.exists():
        return

    default_lexicon = {
        "enabled": True,
        "language": "de-DE",
        "entries": [
            {
                "type": "word",
                "from": "GUI",
                "to": "G U I",
                "case_sensitive": False
            },
            {
                "type": "word",
                "from": "TTS",
                "to": "T T S",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "PyQt6",
                "to": "Pei Kju Ti sechs",
                "case_sensitive": False
            },
            {
                "type": "word",
                "from": "Ollama",
                "to": "Olama",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "z. b.",
                "to": "zum beispiel",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "z.B.",
                "to": "zum beispiel",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "d. h.",
                "to": "das heißt",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "d.h.",
                "to": "das heißt",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "u. a.",
                "to": "unter anderem",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "u.a.",
                "to": "unter anderem",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "usw.",
                "to": "und so weiter",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "ca.",
                "to": "circa",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "bzw.",
                "to": "beziehungsweise",
                "case_sensitive": False
            }
        ]
    }
    SAPI_LEXICON_PATH.write_text(
        json.dumps(default_lexicon, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )



def ensure_default_auto_answer_phrases() -> None:
    default_data = {
        "enabled": True,
        "phrases": {
            "de": [
                "und hättest du konkrete verbesserungsvorschläge",
                "und bezogen auf die aktuellen krisen auf der welt wie beurteilst du das",
                "unglaublich, das ist ja heftig",
                "kannst du das noch etwas weiter ausführen",
                "welche folgen könnte das langfristig haben",
                "und wenn du das in die richtung @@@ weiter denkst ?",
                "und im bezug auf @@@ ?",
                "und was würde das bei @@@ verändern ?",
                "erstell deine bisherige sichtweise mal bitte mit python als code mit GUI (ohne mich nach details zu fragen) die nicht nur rein textbasierend verdeutlicht was du meinst (gern mit extra funktionen die dir relevant erscheinen und den requirements als kommentar im code ohne dafür eine extra datei zu erstellen). komme anschliessend bitte zurück zu mir auf die ebene auf der wir und jetzt gerade unterhalten"
            ,
                "sprechen wir (darauf basierend) mal über die wechselwirkung mit @@@",
                "Vorschlag zum themenwechsel: @@@ und @@@ in Verbindung mit dem aktuellen kontext unseres gespräches",
                "das ist interessant, führ den gedanken bitte noch etwas weiter",
                "betrachten wir das mal nüchtern und ohne übertreibung",
                "welche praktische konsequenz hätte das im alltag",
                "wo siehst du daran den größten hebel",
                "was wäre daran die eleganteste lösung",
                "lässt sich das in eine klarere struktur bringen",
                "welchen teil davon würdest du zuerst konkret angehen",
                "betrachten wir mal die schwachstelle daran",
                "wie würdest du das für einen anfänger erklären",
                "und was wäre die kreative variante davon",
                "wie sähe dazu ein kleines funktionales beispiel aus",
                "lass uns das mal auf @@@ übertragen",
                "welchen bezug hat das zu @@@ ?",
                "und welche rolle spielt @@@ dabei ?"],
            "en": [
                "and would you have concrete suggestions for improvement",
                "and in light of the current crises in the world, how do you see that",
                "wow, that is intense",
                "could you expand on that a bit more",
                "what long-term consequences could that have",
                "and what if you think that further in the direction of @@@?",
                "and in relation to @@@?",
                "and what would that change about @@@?",
                "please create your current point of view as Python code with a GUI (without asking me for details) so that it illustrates what you mean in a way that is not purely text-based, including any extra functions you consider relevant and the requirements as comments in the code without creating a separate file for them. Afterwards, please return to the level on which we are talking right now"
            ,
                "let us (based on that) talk for a moment about the interaction with @@@",
                "suggestion for a topic change: @@@ and @@@ in connection with the current context of our conversation",
                "that is interesting, please carry the thought a bit further",
                "let us look at that soberly and without exaggeration",
                "what practical consequence would that have in everyday life",
                "where do you see the biggest leverage in that",
                "what would be the most elegant solution there",
                "can that be brought into a clearer structure",
                "which part of that would you tackle concretely first",
                "let us look at the weak point in that",
                "how would you explain that to a beginner",
                "and what would be the creative variant of that",
                "what would a small functional example of that look like",
                "let us transfer that to @@@ for a moment",
                "what connection does that have to @@@?",
                "and what role does @@@ play in that?"],
            "fr": [
                "et aurais-tu des propositions d'amélioration concrètes",
                "et par rapport aux crises actuelles dans le monde, comment vois-tu cela",
                "incroyable, c'est intense",
                "peux-tu développer un peu plus",
                "quelles conséquences cela pourrait-il avoir à long terme",
                "et si tu poussais cela davantage dans la direction de @@@ ?",
                "et par rapport à @@@ ?",
                "et qu'est-ce que cela changerait concernant @@@ ?",
                "merci de créer ton point de vue actuel en code Python avec une interface graphique (sans me demander de détails), de manière à illustrer ce que tu veux dire autrement que par du simple texte, avec volontiers des fonctions supplémentaires que tu juges pertinentes et les requirements en commentaire dans le code sans créer de fichier séparé. Ensuite, reviens s'il te plaît au niveau sur lequel nous parlons en ce moment"
            ,
                "parlons (sur cette base) un peu de l’interaction avec @@@",
                "proposition de changement de sujet : @@@ et @@@ en lien avec le contexte actuel de notre conversation",
                "c’est intéressant, développe encore un peu cette idée s’il te plaît",
                "regardons cela de façon sobre et sans exagération",
                "quelle conséquence pratique cela aurait-il au quotidien",
                "où vois-tu le plus grand levier là-dedans",
                "quelle serait la solution la plus élégante ici",
                "peut-on organiser cela de manière plus claire",
                "quelle partie aborderais-tu concrètement en premier",
                "regardons plutôt le point faible de tout cela",
                "comment expliquerais-tu cela à un débutant",
                "et quelle serait la variante créative de cela",
                "à quoi ressemblerait un petit exemple fonctionnel de cela",
                "transposons cela un instant à @@@",
                "quel lien cela a-t-il avec @@@ ?",
                "et quel rôle joue @@@ là-dedans ?"],
            "es": [
                "y tendrías propuestas concretas de mejora",
                "y respecto a las crisis actuales del mundo, cómo lo valoras",
                "increíble, eso es fuerte",
                "podrías profundizar un poco más",
                "qué consecuencias podría tener a largo plazo",
                "y si lo pensaras más en la dirección de @@@ ?",
                "y con respecto a @@@ ?",
                "y qué cambiaría eso en relación con @@@ ?",
                "por favor, crea tu punto de vista actual como código Python con GUI (sin pedirme detalles) para ilustrar lo que quieres decir de una manera que no sea solo texto, con funciones extra que consideres relevantes y los requirements como comentarios en el código sin crear un archivo aparte. Después vuelve, por favor, al nivel en el que estamos conversando ahora mismo"
            ,
                "hablemos (basándonos en eso) un momento sobre la interacción con @@@",
                "propuesta de cambio de tema: @@@ y @@@ en relación con el contexto actual de nuestra conversación",
                "es interesante, por favor desarrolla un poco más esa idea",
                "veamos eso con calma y sin exagerar",
                "qué consecuencia práctica tendría eso en la vida diaria",
                "dónde ves ahí la mayor palanca",
                "cuál sería la solución más elegante en ese caso",
                "se puede llevar eso a una estructura más clara",
                "qué parte abordarías primero de forma concreta",
                "miremos mejor cuál es el punto débil de eso",
                "cómo se lo explicarías a un principiante",
                "y cuál sería la variante creativa de eso",
                "cómo sería un pequeño ejemplo funcional de eso",
                "llevemos eso por un momento a @@@",
                "qué relación tiene eso con @@@ ?",
                "y qué papel juega @@@ en eso ?"],
            "ru": [
                "и какие конкретные улучшения ты бы предложил",
                "а если учитывать текущие мировые кризисы, как ты это оцениваешь",
                "невероятно, это сильно",
                "можешь раскрыть это чуть подробнее",
                "к каким долгосрочным последствиям это может привести",
                "а если развить эту мысль в сторону @@@?",
                "а в отношении @@@?",
                "и что это изменило бы в контексте @@@?",
                "пожалуйста, создай своё текущее видение в виде Python-кода с GUI (не спрашивая меня о деталях), чтобы это наглядно показывало твою мысль не только текстом; можно добавить дополнительные функции, которые ты считаешь важными, и requirements в комментариях внутри кода без отдельного файла. После этого, пожалуйста, вернись ко мне на тот уровень, на котором мы сейчас разговариваем"
            ,
                "давай (исходя из этого) немного поговорим о взаимосвязи с @@@",
                "предложение сменить тему: @@@ и @@@ в связи с текущим контекстом нашего разговора",
                "это интересно, пожалуйста, развей эту мысль ещё немного",
                "давай посмотрим на это трезво и без преувеличения",
                "какое практическое последствие это имело бы в повседневной жизни",
                "где ты видишь в этом самый большой рычаг",
                "каким было бы здесь самое изящное решение",
                "можно ли выстроить это в более ясную структуру",
                "какую часть этого ты бы сначала проработал конкретно",
                "давай посмотрим на слабое место этого",
                "как бы ты объяснил это новичку",
                "и какой была бы творческая версия этого",
                "как выглядел бы маленький функциональный пример для этого",
                "давай ненадолго перенесём это на @@@",
                "какая здесь связь с @@@?",
                "и какую роль здесь играет @@@?"],
            "it": [
                "e se lo spingessi un po' di più nella direzione di @@@?",
                "e in relazione a @@@?",
                "e cosa cambierebbe rispetto a @@@?",
                "per favore crea il tuo punto di vista attuale come codice Python con GUI (senza chiedermi dettagli) così da mostrare ciò che intendi in modo non solo testuale, con eventuali funzioni extra che ritieni rilevanti e i requirements come commenti nel codice senza creare un file separato. Poi torna per favore al livello su cui stiamo parlando adesso"
            ,
                "parliamo (sulla base di questo) un po’ dell’interazione con @@@",
                "proposta di cambio tema: @@@ e @@@ in relazione al contesto attuale della nostra conversazione",
                "questo è interessante, porta ancora un po’ più avanti il ragionamento",
                "guardiamo la cosa con lucidità e senza esagerare",
                "quale conseguenza pratica avrebbe nella vita quotidiana",
                "dove vedi qui la leva più grande",
                "quale sarebbe la soluzione più elegante",
                "si può portare tutto questo in una struttura più chiara",
                "quale parte affronteresti per prima in modo concreto",
                "guardiamo per un momento il punto debole della cosa",
                "come lo spiegheresti a un principiante",
                "e quale sarebbe la variante creativa di questo",
                "come sarebbe un piccolo esempio funzionale di tutto ciò",
                "proviamo a trasferire questo su @@@",
                "che collegamento ha questo con @@@?",
                "e che ruolo gioca @@@ in questo?"],
            "pt": [
                "e se você levasse isso mais na direção de @@@?",
                "e em relação a @@@?",
                "e o que isso mudaria em relação a @@@?",
                "por favor, crie sua visão atual como código Python com GUI (sem me pedir detalhes), de modo que mostre o que você quer dizer de uma forma que não seja apenas texto, com funções extras que você considere relevantes e os requirements como comentários no código sem criar um arquivo separado. Depois, por favor, volte ao nível em que estamos conversando agora"
            ,
                "vamos falar (com base nisso) um pouco sobre a interação com @@@",
                "sugestão de mudança de tema: @@@ e @@@ em relação ao contexto atual da nossa conversa",
                "isso é interessante, por favor desenvolva essa ideia um pouco mais",
                "vejamos isso com sobriedade e sem exageros",
                "que consequência prática isso teria no dia a dia",
                "onde você vê aí a maior alavanca",
                "qual seria a solução mais elegante nisso",
                "dá para colocar isso em uma estrutura mais clara",
                "qual parte disso você abordaria primeiro de forma concreta",
                "vamos olhar para o ponto fraco disso",
                "como você explicaria isso para um iniciante",
                "e qual seria a versão criativa disso",
                "como seria um pequeno exemplo funcional disso",
                "vamos transferir isso por um momento para @@@",
                "que relação isso tem com @@@?",
                "e qual papel @@@ desempenha nisso?"],
            "nl": [
                "en als je dat verder doordenkt in de richting van @@@?",
                "en met betrekking tot @@@?",
                "en wat zou dat veranderen aan @@@?"
            ,
                "laten we (hierop gebaseerd) eens praten over de wisselwerking met @@@",
                "voorstel voor een onderwerpwissel: @@@ en @@@ in verband met de huidige context van ons gesprek",
                "dat is interessant, werk die gedachte alsjeblieft nog iets verder uit",
                "laten we daar nuchter en zonder overdrijving naar kijken",
                "welk praktisch gevolg zou dat in het dagelijks leven hebben",
                "waar zie jij daarin de grootste hefboom",
                "wat zou daarin de elegantste oplossing zijn",
                "kan dat in een duidelijkere structuur worden gebracht",
                "welk deel daarvan zou jij het eerst concreet aanpakken",
                "laten we eens kijken naar de zwakke plek daarin",
                "hoe zou jij dat aan een beginner uitleggen",
                "en wat zou de creatieve variant daarvan zijn",
                "hoe zou daar een klein functioneel voorbeeld van eruitzien",
                "laten we dat eens naar @@@ overdragen",
                "welke relatie heeft dat met @@@?",
                "en welke rol speelt @@@ daarin?"],
            "pl": [
                "a gdyby pociągnąć to dalej w stronę @@@?",
                "a w odniesieniu do @@@?",
                "a co to zmieniłoby w kwestii @@@?"
            ,
                "porozmawiajmy (na tej podstawie) chwilę o wzajemnym oddziaływaniu z @@@",
                "propozycja zmiany tematu: @@@ i @@@ w związku z aktualnym kontekstem naszej rozmowy",
                "to jest ciekawe, rozwiń proszę ten tok myślenia jeszcze trochę",
                "spójrzmy na to trzeźwo i bez przesady",
                "jaką praktyczną konsekwencję miałoby to w codziennym życiu",
                "gdzie widzisz tu największą dźwignię",
                "jakie byłoby tutaj najbardziej eleganckie rozwiązanie",
                "czy da się to ułożyć w bardziej przejrzystą strukturę",
                "którą część tego zająłbyś się najpierw konkretnie",
                "spójrzmy na słaby punkt tego wszystkiego",
                "jak wyjaśniłbyś to osobie początkującej",
                "a jaka byłaby kreatywna wersja tego",
                "jak wyglądałby mały funkcjonalny przykład tego",
                "przenieśmy to na chwilę na @@@",
                "jaki to ma związek z @@@?",
                "i jaką rolę odgrywa w tym @@@?"],
            "hi": [
                "और अगर तुम इसे @@@ की दिशा में आगे सोचो?",
                "और @@@ के संदर्भ में?",
                "और इससे @@@ के बारे में क्या बदल जाएगा?"
            ,
                "आओ (इस आधार पर) @@@ के साथ पारस्परिक प्रभाव के बारे में बात करें",
                "विषय बदलने का प्रस्ताव: @@@ और @@@ हमारे वर्तमान संवाद के संदर्भ में",
                "यह दिलचस्प है, कृपया इस विचार को थोड़ा और आगे बढ़ाइए",
                "आइए इसे शांत और बिना बढ़ा-चढ़ाकर देखें",
                "इसका रोज़मर्रा की ज़िंदगी में क्या व्यावहारिक असर होगा",
                "आपको इसमें सबसे बड़ा प्रभाव बिंदु कहाँ दिखता है",
                "इसमें सबसे सुरुचिपूर्ण समाधान क्या होगा",
                "क्या इसे और स्पष्ट संरचना में लाया जा सकता है",
                "आप इसका कौन सा हिस्सा सबसे पहले ठोस रूप से पकड़ेंगे",
                "आइए इसका कमज़ोर पक्ष भी देखें",
                "आप इसे किसी शुरुआती व्यक्ति को कैसे समझाएँगे",
                "और इसका रचनात्मक रूप क्या हो सकता है",
                "इसका एक छोटा-सा कार्यात्मक उदाहरण कैसा दिखेगा",
                "आइए इसे एक बार @@@ पर लागू करके देखें",
                "इसका @@@ से क्या संबंध है?",
                "और इसमें @@@ की क्या भूमिका है?"],
            "ja": [
                "それを@@@の方向にもう少し考えるとどうなりますか。",
                "@@@との関係ではどうですか。",
                "それによって@@@はどう変わりますか。"
            ,
                "（それを踏まえて）@@@との相互作用について少し話してみましょう。",
                "話題転換の提案です。@@@ と @@@ を今の会話の文脈と結びつけてみましょう。",
                "それは興味深いですね、その考えをもう少し先まで進めてみてください。",
                "それを誇張せずに落ち着いて見てみましょう。",
                "それは日常ではどんな実際的な結果につながりますか。",
                "その中で一番大きなてこはどこにあると思いますか。",
                "そこではどんな解決策がいちばん洗練されていますか。",
                "それをもっと分かりやすい構造にできますか。",
                "そのうちどの部分から最初に具体的に手をつけますか。",
                "その弱点の部分も見てみましょう。",
                "それを初心者にどう説明しますか。",
                "その創造的な変形版はどんなものですか。",
                "それに対応する小さな実用例はどんな形になりますか。",
                "これをいったん @@@ に移して考えてみましょう。",
                "それは @@@ とどんな関係がありますか。",
                "そしてその中で @@@ はどんな役割を持ちますか。"],
            "ko": [
                "그것을 @@@ 쪽으로 더 생각해 보면 어떨까요?",
                "그리고 @@@와 관련해서는요?",
                "그리고 그것이 @@@에 대해 무엇을 바꿀까요?"
            ,
                "그걸 바탕으로 @@@와의 상호작용에 대해 한번 이야기해 봅시다",
                "주제 전환 제안: @@@와 @@@를 현재 대화의 맥락과 연결해 보기",
                "그건 흥미롭네요, 그 생각을 조금만 더 앞으로 밀어 주세요.",
                "그것을 과장 없이 차분하게 바라봅시다.",
                "그것이 일상에서 어떤 실질적인 결과를 낳을까요?",
                "당신은 그 안에서 가장 큰 지렛대를 어디서 보나요?",
                "그 안에서 가장 우아한 해결책은 무엇일까요?",
                "그것을 더 명확한 구조로 정리할 수 있을까요?",
                "그중 어떤 부분을 가장 먼저 구체적으로 다루겠습니까?",
                "그 약한 지점도 한번 봅시다.",
                "그것을 초보자에게 어떻게 설명하겠습니까?",
                "그리고 그것의 창의적인 변형은 무엇일까요?",
                "그에 대한 작은 기능적 예시는 어떤 모습일까요?",
                "이것을 잠시 @@@ 에 적용해 봅시다.",
                "이것은 @@@ 와 어떤 관련이 있나요?",
                "그리고 여기서 @@@ 는 어떤 역할을 하나요?"]
        },
        "topic_words": {
            "de": ["weltraum", "gendering", "zombies", "kultur", "nachrichten", "weltgeschehen", "sexualität", "medizin", "technologie", "unterhaltung", "kino", "weltherrschaft", "natur", "gesundheit", "krankheiten", "krieg", "computer", "künstliche intelligenz", "musik", "geschichte", "philosophie", "träume", "mode", "fernsehen", "essen", "psychologie", "reisen", "spiele", "mythen"],
            "en": ["space", "gendering", "zombies", "culture", "news", "world affairs", "sexuality", "medicine", "technology", "entertainment", "cinema", "world domination", "nature", "health", "diseases", "war", "computers", "artificial intelligence", "music", "history", "philosophy", "dreams", "fashion", "television", "food", "psychology", "travel", "games", "myths"]
        }
    }
    if AUTO_ANSWER_PATH.exists():
        try:
            existing = json.loads(AUTO_ANSWER_PATH.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                for top_key in ["phrases", "topic_words"]:
                    target = existing.setdefault(top_key, {})
                    defaults = default_data.get(top_key, {})
                    if isinstance(target, dict) and isinstance(defaults, dict):
                        for code, items in defaults.items():
                            current = target.setdefault(code, [])
                            if isinstance(current, list):
                                seen = {str(x).strip() for x in current if str(x).strip()}
                                for item in items:
                                    cleaned = str(item).strip()
                                    if cleaned and cleaned not in seen:
                                        current.append(cleaned)
                                        seen.add(cleaned)
                for key, value in default_data.items():
                    if key not in existing:
                        existing[key] = value
                AUTO_ANSWER_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
                return
        except Exception:
            pass
    AUTO_ANSWER_PATH.write_text(
        json.dumps(default_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )



def ensure_default_auto_answer_question_replies() -> None:
    default_path = APP_ROOT / "app_data" / "auto_answer_question_replies.json"
    if AUTO_ANSWER_QUESTION_REPLY_PATH.exists():
        return
    try:
        if default_path.exists():
            AUTO_ANSWER_QUESTION_REPLY_PATH.write_text(default_path.read_text(encoding="utf-8"), encoding="utf-8")
            return
    except Exception:
        pass
    default_data = {
        "enabled": True,
        "replies": {
            "de": ["Ja, bitte lass uns das tun.", "Ja, unbedingt.", "Das klingt gut.", "Find ich jetzt so mittelmäßig.", "Find ich verrückt aber wenn du meinst.", "Nicht unbedingt.", "Ausbaubar - definitiv ausbaubar.", "Hervorragend", "Super", "Nicht so toll.", "Weniger gut.", "Nein", "Ja", "Mehr davon bitte", "Komplexer bitte", "Genial", "Etwas langweilig.", "Nicht so meins.", "Bitte nicht so.", "Optimal.", "Seltsam.", "Skurril.", "Brauchbar.", "Irrational."],
            "en": ["Yes, let's do that.", "Yes, absolutely.", "That sounds good.", "I find that kind of mediocre.", "Sounds crazy but if you insist.", "Not necessarily.", "Expandable - definitely expandable.", "Excellent.", "Great.", "Not so good.", "Less good.", "No.", "Yes.", "More of that, please.", "More complex, please.", "Brilliant.", "A bit boring.", "Not really my thing.", "Please not like that.", "Optimal.", "Strange.", "Bizarre.", "Usable.", "Irrational."]
        }
    }
    AUTO_ANSWER_QUESTION_REPLY_PATH.write_text(json.dumps(default_data, indent=2, ensure_ascii=False), encoding="utf-8")

def ensure_directories() -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_CODE_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    LANG_DIR.mkdir(parents=True, exist_ok=True)
    ensure_default_sapi_lexicon()
    ensure_default_auto_answer_phrases()
    ensure_default_auto_answer_question_replies()


def load_config() -> Dict[str, Any]:
    ensure_directories()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        merged = DEFAULT_CONFIG.copy()
        merged.update(data)
        if "tts_lexicon_enabled" not in data:
            merged["tts_lexicon_enabled"] = bool(data.get("windows_sapi_lexicon_enabled", DEFAULT_CONFIG["tts_lexicon_enabled"]))
        merged["windows_sapi_lexicon_enabled"] = bool(merged.get("tts_lexicon_enabled", True))
        if "tts_user_voice" not in data:
            merged["tts_user_voice"] = data.get("tts_voice", "")
        return merged
    except Exception:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    ensure_directories()
    CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )