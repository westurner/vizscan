import os
import re
import enum
import argparse
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

# --- UI HANDLING ---
try:
    from rich.console import Console  # type: ignore

    console = Console()
except ImportError:

    class MockConsole:
        def print(self, *args, **kwargs):
            print(*args)

    console = MockConsole()

# ==========================================
# 1. ONTOLOGY & REGISTRY
# ==========================================


class RiskLevel(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    BAN = "BAN"


@dataclass
class RiskEvent:
    rule_id: str
    risk_level: RiskLevel
    score: int
    context: str
    line: int
    variables: List[str]
    source_type: str = "CPU"  # 'CPU' or 'GPU'
    timecode: Optional[float] = None


@dataclass
class Reason:
    name: str
    url: str


@dataclass
class RuleDefinition:
    id: str
    name: str
    description: str
    base_score: int
    level: RiskLevel
    reasons: List[Reason] = field(default_factory=list)


class SafetyRegistry:
    def __init__(self):
        self.rules = {}

    def register(self, r_id, name, desc, score, level, reasons=None):
        if reasons is None:
            reasons = []
        self.rules[r_id] = RuleDefinition(r_id, name, desc, score, level, reasons)

    def create_event(self, rule_id, context, line, vars, src_type="CPU"):
        if rule_id not in self.rules:
            return RiskEvent(rule_id, RiskLevel.INFO, 0, context, line, vars, src_type)
        r = self.rules[rule_id]
        return RiskEvent(rule_id, r.level, r.base_score, context, line, vars, src_type)

    def export_ontology(self):
        return [
            {
                "@id": f"pes:{r.id}",
                "dct:title": r.name,
                "dct:description": r.description,
                "pes:score": r.base_score,
                "pes:level": r.level,
                "pes:reasons": [
                    {"name": reason.name, "url": reason.url} for reason in r.reasons
                ],
            }
            for r in self.rules.values()
        ]


REGISTRY = SafetyRegistry()
REGISTRY.register(
    "InverterStrobe",
    "Hard Strobe",
    "val = 1 - val (30Hz strobe)",
    150,
    RiskLevel.BAN,
    reasons=[
        Reason(
            name="ITU-R BT.1702 (rapid alternating light/dark frames exceeding safe flash threshold)",
            url="https://www.itu.int/rec/R-REC-BT.1702/en",
        )
    ],
)
REGISTRY.register(
    "FrameModulo",
    "Frame Modulo",
    "frame % N (Rapid flicker)",
    100,
    RiskLevel.CRITICAL,
    reasons=[
        Reason(name="ITU-R BT.1702", url="https://www.itu.int/rec/R-REC-BT.1702/en"),
        Reason(
            name="WCAG 2.1 General Flash Threshold (>3Hz)",
            url="https://www.w3.org/TR/WCAG21/#three-flashes-or-below-threshold",
        ),
    ],
)
REGISTRY.register(
    "HighFreqOsc",
    "High Frequency",
    "Oscillation > 3Hz",
    40,
    RiskLevel.WARNING,
    reasons=[
        Reason(name="ITU-R BT.1702", url="https://www.itu.int/rec/R-REC-BT.1702/en"),
        Reason(
            name="WCAG 2.1 General Flash Threshold",
            url="https://www.w3.org/TR/WCAG21/#three-flashes-or-below-threshold",
        ),
    ],
)
REGISTRY.register(
    "TanColor",
    "Tangent Color",
    "Tan() on color (Flash Risk)",
    60,
    RiskLevel.CRITICAL,
    reasons=[
        Reason(
            name="ITU-R BT.1702 (high-contrast luminance transitions)",
            url="https://www.itu.int/rec/R-REC-BT.1702/en",
        )
    ],
)
REGISTRY.register(
    "TanMotion",
    "Tangent Motion",
    "Tan() on geometry (Disorientation Risk)",
    30,
    RiskLevel.WARNING,
    reasons=[
        Reason(
            name="ITU-R BT.1702 (provocative spatial patterns and disorientation)",
            url="https://www.itu.int/rec/R-REC-BT.1702/en",
        )
    ],
)
REGISTRY.register(
    "StepFunction",
    "Hard Step Edge",
    "Step/Fract function creating instant on/off",
    50,
    RiskLevel.WARNING,
    reasons=[
        Reason(
            name="ITU-R BT.1702 (high-contrast luminance transitions)",
            url="https://www.itu.int/rec/R-REC-BT.1702/en",
        )
    ],
)

# ==========================================
# 2. AST NODES
# ==========================================


@dataclass(frozen=True, slots=True)
class Node:
    line: int


@dataclass(frozen=True, slots=True)
class Program(Node):
    statements: List[Node]


@dataclass(frozen=True, slots=True)
class Block(Node):
    statements: List[Node]


@dataclass(frozen=True, slots=True)
class Assignment(Node):
    target: str
    expr: Node
    is_decl: bool = False


@dataclass(frozen=True, slots=True)
class BinaryOp(Node):
    left: Node
    op: str
    right: Node


@dataclass(frozen=True, slots=True)
class FunctionCall(Node):
    name: str
    args: List[Node]


@dataclass(frozen=True, slots=True)
class Literal(Node):
    value: float


@dataclass(frozen=True, slots=True)
class Identifier(Node):
    name: str


@dataclass(frozen=True, slots=True)
class MemberAccess(Node):
    expr: Node
    member: str  # For GLSL swizzling (col.rgb)


# ==========================================
# 3. LEXER (Updated for C-Style Syntax)
# ==========================================

TOKEN_TYPES = [
    ("COMMENT", r"//.*|/\*[\s\S]*?\*/"),
    ("NUMBER", r"\d+(\.\d*)?"),
    ("TYPE", r"\b(float|int|vec2|vec3|vec4|float2|float3|float4)\b"),  # GLSL/HLSL Types
    ("ID", r"[a-zA-Z_][a-zA-Z0-9_]*"),
    ("ASSIGN", r"="),
    ("OP", r"[+\-*/%^]"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("LBRACE", r"\{"),
    ("RBRACE", r"\}"),  # Blocks
    ("DOT", r"\."),  # Swizzling
    ("COMMA", r","),
    ("SEMICOLON", r";"),
    ("SKIP", r"[ \t]+"),
    ("NEWLINE", r"\n"),
    ("MISMATCH", r"."),
]


@dataclass(frozen=True, slots=True)
class Token:
    type: str
    value: str
    line: int


class MilkLexer:
    def __init__(self, code):
        self.code = code
        self.line_num = 1
        self.tokens = []
        self.pos = 0

    def tokenize(self):
        pos = 0
        while pos < len(self.code):
            match = None
            for token_type, regex in TOKEN_TYPES:
                pattern = re.compile(regex)
                match = pattern.match(self.code, pos)
                if match:
                    text = match.group(0)
                    if token_type == "NEWLINE":
                        self.line_num += 1
                    elif token_type != "SKIP" and token_type != "COMMENT":
                        self.tokens.append(Token(token_type, text, self.line_num))
                    pos = match.end()
                    break
            if not match:
                pos += 1  # Skip mismatch
        return self.tokens


# ==========================================
# 4. PARSER
# ==========================================


class MilkParser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def consume(self, expected_type=None):
        if self.pos < len(self.tokens):
            token = self.tokens[self.pos]
            if expected_type and token.type != expected_type:
                return None
            self.pos += 1
            return token
        return None

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def parse(self):
        statements = []
        while self.pos < len(self.tokens):
            stmt = self.parse_statement()
            if stmt:
                statements.append(stmt)
            else:
                self.pos += 1
        return Program(line=1, statements=statements)

    def parse_statement(self):
        token = self.peek()
        if not token:
            return None

        if token.type == "LBRACE":
            return self.parse_block()

        if token.type == "TYPE":
            # float x = ...;
            self.consume()  # type
            target = self.consume("ID")
            if not target:
                return None

            expr = Literal(token.line, 0)
            peek_token = self.peek()
            if peek_token and peek_token.type == "ASSIGN":
                self.consume("ASSIGN")
                expr = self.parse_expression()

            self.consume("SEMICOLON")
            return Assignment(token.line, target.value, expr, is_decl=True)

        if token.type == "ID":
            # x = ...;
            target = self.consume("ID")
            peek_token = self.peek()
            if target and peek_token and peek_token.type == "ASSIGN":
                self.consume("ASSIGN")
                expr = self.parse_expression()
                self.consume("SEMICOLON")
                return Assignment(token.line, target.value, expr)
            # Function call as statement? or just expression
            # For now assume assignment is main statement type

        return None

    def parse_block(self):
        token = self.consume("LBRACE")
        if not token:
            return None
        stmts = []
        while True:
            peek_token = self.peek()
            if not peek_token or peek_token.type == "RBRACE":
                break
            s = self.parse_statement()
            if s:
                stmts.append(s)
            else:
                self.pos += 1
        self.consume("RBRACE")
        return Block(token.line, stmts)

    def parse_expression(self):
        left = self.parse_term()
        while True:
            peek_token = self.peek()
            if not peek_token or peek_token.type != "OP":
                break
            op_token = self.consume("OP")
            op = op_token.value if op_token else ""
            right = self.parse_term()
            left = BinaryOp(left.line, left, op, right)
        return left

    def parse_term(self):
        token = self.peek()
        if not token:
            return Literal(0, 0)

        if token.type == "NUMBER":
            num_token = self.consume()
            val = float(num_token.value) if num_token else 0.0
            return Literal(token.line, val)

        if token.type == "ID":
            id_token = self.consume()
            name = id_token.value if id_token else ""
            peek_token = self.peek()
            if peek_token and peek_token.type == "LPAREN":
                # Function Call or Constructor
                self.consume("LPAREN")
                args = self.parse_arg_list()
                self.consume("RPAREN")
                return FunctionCall(token.line, name, args)

            # Swizzling check
            node = Identifier(token.line, name)
            while True:
                peek_token = self.peek()
                if not peek_token or peek_token.type != "DOT":
                    break
                self.consume("DOT")
                member = self.consume("ID")
                if member:
                    node = MemberAccess(token.line, node, member.value)
            return node

        if token.type == "LPAREN":
            self.consume()
            expr = self.parse_expression()
            self.consume("RPAREN")
            return expr

        self.consume()
        return Literal(token.line, 0)

    def parse_arg_list(self):
        args = []
        peek_token = self.peek()
        if peek_token and peek_token.type != "RPAREN":
            args.append(self.parse_expression())
            while True:
                peek_token = self.peek()
                if not peek_token or peek_token.type != "COMMA":
                    break
                self.consume("COMMA")
                args.append(self.parse_expression())
        return args


# ==========================================
# 5. TAINT ANALYSIS
# ==========================================


@dataclass
class TaintState:
    is_time_dep: bool = False
    freq: float = 0.0
    hard_edge: bool = False
    source: str = ""


class SafetyAnalyzer:
    COLOR_VARS = {
        "ob_r",
        "ob_g",
        "ob_b",
        "wave_r",
        "wave_g",
        "wave_b",
        "gl_FragColor",
        "ret",
    }
    MOTION_VARS = {"rot", "zoom", "warp", "cx", "cy", "dx", "dy", "sx", "sy"}

    def __init__(self, context="CPU"):
        self.events = []
        self.context = context
        self.symbols = {}
        self.symbols["time"] = TaintState(is_time_dep=True, freq=1.0)
        self.symbols["frame"] = TaintState(is_time_dep=True, hard_edge=True)

    def get_taint(self, name):
        return self.symbols.get(name, TaintState())

    def analyze(self, node):
        if isinstance(node, Program) or isinstance(node, Block):
            for stmt in node.statements:
                self.analyze(stmt)
        elif isinstance(node, Assignment):
            self.visit_Assignment(node)
        # Expressions are visited via assignments

    def visit(self, node):
        if isinstance(node, Literal):
            return TaintState()
        if isinstance(node, Identifier):
            return self.get_taint(node.name)
        if isinstance(node, BinaryOp):
            left_node = self.visit(node.left)
            right_node = self.visit(node.right)

            freq = max(left_node.freq, right_node.freq)
            if node.op == "*":
                # Check for time * constant
                if left_node.is_time_dep and isinstance(node.right, Literal):
                    freq = left_node.freq * node.right.value
                elif right_node.is_time_dep and isinstance(node.left, Literal):
                    freq = right_node.freq * node.left.value

            return TaintState(
                is_time_dep=left_node.is_time_dep or right_node.is_time_dep,
                freq=freq,
                hard_edge=left_node.hard_edge or right_node.hard_edge,
            )
        if isinstance(node, FunctionCall):
            args = [self.visit(a) for a in node.args]
            primary = args[0] if args else TaintState()

            if node.name in ["sin", "cos"]:
                if primary.freq > 18.0:
                    # HighFreqOsc: 18 rad/s is ~2.86 Hz, approaching the 3Hz limit.
                    # Cite WCAG 2.1 General Flash Threshold and ITU-R BT.1702.
                    self.events.append(
                        REGISTRY.create_event(
                            "HighFreqOsc",
                            f"{node.name}(freq={primary.freq:.1f})",
                            node.line,
                            [node.name],
                            self.context,
                        )
                    )
                return TaintState(is_time_dep=True, freq=primary.freq)

            if node.name == "tan":
                return TaintState(is_time_dep=True, hard_edge=True, source="tan")

            if node.name in ["step", "fract", "ceil", "floor"]:
                if primary.is_time_dep:
                    # StepFunction: Creates instant on/off hard edges in time, leading to infinite-contrast flashes.
                    # Cite ITU-R BT.1702 regarding high-contrast luminance transitions.
                    self.events.append(
                        REGISTRY.create_event(
                            "StepFunction",
                            f"{node.name}() on time",
                            node.line,
                            [node.name],
                            self.context,
                        )
                    )
                return TaintState(is_time_dep=True, hard_edge=True, source=node.name)

            return primary

        if isinstance(node, MemberAccess):
            return self.visit(node.expr)

        return TaintState()

    def visit_Assignment(self, node):
        expr_state = self.visit(node.expr)

        # Inverter Strobe: x = 1 - x
        # Creates a guaranteed 30Hz strobe (at 60fps).
        # Cite ITU-R BT.1702 regarding rapid alternating light/dark frames exceeding the safe flash threshold.
        if isinstance(node.expr, BinaryOp) and node.expr.op == "-":
            # Check if right side is the target variable
            if (
                isinstance(node.expr.right, Identifier)
                and node.expr.right.name == node.target
            ):
                self.events.append(
                    REGISTRY.create_event(
                        "InverterStrobe",
                        f"{node.target} = 1 - {node.target}",
                        node.line,
                        [node.target],
                        self.context,
                    )
                )

        # Frame Modulo
        # Creates rapid flickering.
        # Cite ITU-R BT.1702 and WCAG 2.1 General Flash Threshold (exceeds 3Hz).
        if isinstance(node.expr, BinaryOp) and node.expr.op == "%":
            if isinstance(node.expr.right, Literal) and node.expr.right.value < 4:
                self.events.append(
                    REGISTRY.create_event(
                        "FrameModulo",
                        f"Modulo {node.expr.right.value}",
                        node.line,
                        [node.target],
                        self.context,
                    )
                )

        # Tan Color
        # Tangent functions approach infinity, causing sudden, extreme high-contrast whiteouts.
        # Cite ITU-R BT.1702 regarding high-contrast luminance transitions and WCAG 2.1.
        if node.target in self.COLOR_VARS:
            if expr_state.source == "tan":
                self.events.append(
                    REGISTRY.create_event(
                        "TanColor",
                        f"Tan -> {node.target}",
                        node.line,
                        [node.target],
                        self.context,
                    )
                )

        # Tan Motion
        # Causes extreme, sudden spatial jumps.
        # Cite ITU-R BT.1702 regarding provocative spatial patterns and disorientation.
        if node.target in self.MOTION_VARS:
            if expr_state.source == "tan":
                self.events.append(
                    REGISTRY.create_event(
                        "TanMotion",
                        f"Tan -> {node.target}",
                        node.line,
                        [node.target],
                        self.context,
                    )
                )

        self.symbols[node.target] = expr_state
        return expr_state


# ==========================================
# 6. QUALITY ANALYSIS
# ==========================================


@dataclass
class QualityReport:
    background_type: str = "Unknown"  # Dark, Light, Dynamic
    avg_brightness_est: float = 0.0
    is_grayscale: bool = False
    attributes: List[str] = field(default_factory=list)


class QualityAnalyzer:
    def __init__(self):
        self.bg_color: Dict[str, Optional[float]] = {"r": None, "g": None, "b": None}
        self.is_dynamic_bg = False
        self.assignments = {}

    def analyze(self, node):
        if isinstance(node, Program) or isinstance(node, Block):
            for stmt in node.statements:
                self.analyze(stmt)
        elif isinstance(node, Assignment):
            self.visit_Assignment(node)

    def visit_Assignment(self, node):
        # Track background color (ob_r, ob_g, ob_b)
        if node.target in ["ob_r", "ob_g", "ob_b"]:
            if isinstance(node.expr, Literal):
                self.bg_color[node.target[-1]] = node.expr.value
            else:
                self.is_dynamic_bg = True

        self.assignments[node.target] = node.expr

    def generate_report(self) -> QualityReport:
        report = QualityReport()

        # Background Analysis
        if self.is_dynamic_bg:
            report.background_type = "Dynamic"
            report.attributes.append("Dynamic Background")
        else:
            r = self.bg_color.get("r")
            g = self.bg_color.get("g")
            b = self.bg_color.get("b")

            if r is not None and g is not None and b is not None:
                lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
                report.avg_brightness_est = lum
                if lum < 0.1:
                    report.background_type = "Dark"
                    report.attributes.append("Dark Background")
                elif lum > 0.9:
                    report.background_type = "Light"
                    report.attributes.append("Light Background")
                else:
                    report.background_type = "Medium"
            else:
                # Default in MilkDrop is usually black if not set? Or preserved?
                # Assuming unknown if not fully set
                pass

        return report


# ==========================================
# 7. SCANNER ORCHESTRATION
# ==========================================


def extract_shaders(milk_code: str) -> Dict[str, str]:
    shaders = {}
    for shader_type in ["warp", "comp"]:
        pattern = re.compile(f'{shader_type}_shader\\s*=\\s*"(.*?)";', re.DOTALL)
        match = pattern.search(milk_code)
        if match:
            shaders[shader_type] = (
                match.group(1).replace('\\"', '"').replace("\\n", "\n")
            )
    return shaders


def parse_metadata(code: str) -> Dict[str, int]:
    metadata = {}
    for line in code.splitlines():
        line = line.strip()
        if not line.startswith("//"):
            continue

        # Format: // Expect: RuleID=Count, RuleID2=Count
        if "Expect:" in line:
            try:
                _, content = line.split("Expect:", 1)
                parts = content.split(",")
                for part in parts:
                    if "=" in part:
                        key, val = part.split("=", 1)
                        metadata[key.strip()] = int(val.strip())
            except ValueError:
                pass
    return metadata


def scan_file_full(
    filepath: str,
) -> Tuple[List[RiskEvent], Dict[str, int], QualityReport]:
    all_events = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            full_code = f.read()
    except Exception:
        return [], {}, QualityReport()

    metadata = parse_metadata(full_code)

    # CPU Analysis
    lexer = MilkLexer(full_code)
    ast = MilkParser(lexer.tokenize()).parse()

    # Safety Analysis
    cpu_ana = SafetyAnalyzer("CPU")
    cpu_ana.analyze(ast)
    all_events.extend(cpu_ana.events)

    # Quality Analysis
    qual_ana = QualityAnalyzer()
    qual_ana.analyze(ast)
    quality_report = qual_ana.generate_report()

    # GPU Analysis
    shaders = extract_shaders(full_code)
    for s_type, s_code in shaders.items():
        if not s_code.strip():
            continue

        lexer = MilkLexer(s_code)
        ast = MilkParser(lexer.tokenize()).parse()
        gpu_ana = SafetyAnalyzer(f"GPU:{s_type}")
        gpu_ana.analyze(ast)
        all_events.extend(gpu_ana.events)

    return all_events, metadata, quality_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="File to scan")
    args = parser.parse_args()

    if os.path.isfile(args.path):
        events, _, quality = scan_file_full(args.path)
        for e in events:
            print(f"[{e.risk_level}] {e.source_type} Line {e.line}: {e.context}")

        print("\nQuality Report:")
        print(f"  Background: {quality.background_type}")
        print(f"  Attributes: {', '.join(quality.attributes)}")


if __name__ == "__main__":
    main()
