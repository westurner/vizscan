import pytest
import sys
from unittest.mock import patch
from vizscan.static import (
    MilkLexer,
    MilkParser,
    SafetyAnalyzer,
    extract_shaders,
    Token,
    Assignment,
    FunctionCall,
    Block,
    Program,
    RiskEvent,
    SafetyRegistry,
    RiskLevel,
    scan_file_full,
    parse_metadata,
    Literal,
    Identifier,
    BinaryOp,
    QualityAnalyzer,
    MemberAccess,
)

# ==========================================
# 1. LEXER TESTS
# ==========================================


def test_lexer_types_and_blocks():
    code = "float x; { vec3 y; }"
    lexer = MilkLexer(code)
    tokens = lexer.tokenize()

    types = [t.type for t in tokens]
    # Expected: TYPE ID SEMICOLON LBRACE TYPE ID SEMICOLON RBRACE
    assert types == [
        "TYPE",
        "ID",
        "SEMICOLON",
        "LBRACE",
        "TYPE",
        "ID",
        "SEMICOLON",
        "RBRACE",
    ]
    assert tokens[0].value == "float"
    assert tokens[4].value == "vec3"


def test_lexer_swizzling():
    code = "col.rgb"
    lexer = MilkLexer(code)
    tokens = lexer.tokenize()
    assert [t.type for t in tokens] == ["ID", "DOT", "ID"]


# ==========================================
# 2. PARSER TESTS
# ==========================================


def test_parser_variable_declaration():
    code = "float x = 1.0;"
    parser = MilkParser(MilkLexer(code).tokenize())
    program = parser.parse()

    stmt = program.statements[0]
    assert isinstance(stmt, Assignment)
    assert stmt.is_decl is True
    assert stmt.target == "x"


def test_parser_block():
    code = "{ x = 1.0; }"
    parser = MilkParser(MilkLexer(code).tokenize())
    program = parser.parse()

    block = program.statements[0]
    assert isinstance(block, Block)


# --- PES SHADER SCANNER COVERAGE ---


def test_registry_unknown_rule():
    reg = SafetyRegistry()
    event = reg.create_event("UnknownRule", "ctx", 1, [])
    assert event.risk_level == RiskLevel.INFO


def test_lexer_mismatch():
    code = "x = @;"  # @ is invalid
    lexer = MilkLexer(code)
    tokens = lexer.tokenize()
    # Should skip @ and tokenize ;
    assert (
        len(tokens) == 4
    )  # ID, ASSIGN, SEMICOLON (SKIP is ignored) -> Wait, @ is skipped
    # x, =, ; -> 3 tokens
    types = [t.type for t in tokens]
    assert "ID" in types
    assert "ASSIGN" in types
    assert "SEMICOLON" in types


def test_parser_consume_mismatch():
    tokens = MilkLexer("x = 1;").tokenize()
    parser = MilkParser(tokens)
    # Expecting TYPE but got ID
    assert parser.consume("TYPE") is None


def test_parser_eof():
    parser = MilkParser([])
    assert parser.parse_statement() is None
    term = parser.parse_term()
    assert isinstance(term, Literal)
    assert term.value == 0


def test_parser_incomplete_decl():
    # float; (missing ID)
    tokens = MilkLexer("float;").tokenize()
    parser = MilkParser(tokens)
    assert parser.parse_statement() is None


def test_parser_block_error():
    tokens = MilkLexer("}").tokenize()  # No LBRACE
    parser = MilkParser(tokens)
    # parse_block expects to be called when LBRACE is peeked,
    # but if we call it manually:
    assert parser.parse_block() is None


def test_parser_expression_statement():
    # x; (valid expression statement in C, but our parser might return None if not assignment)
    tokens = MilkLexer("x;").tokenize()
    parser = MilkParser(tokens)
    # Current parser implementation returns None for non-assignment statements
    assert parser.parse_statement() is None


def test_analyzer_binary_op_coverage():
    ana = SafetyAnalyzer()
    # Test * with no time dependency
    node = BinaryOp(1, Literal(1, 2.0), "*", Literal(1, 3.0))
    state = ana.visit(node)
    assert not state.is_time_dep
    assert state.freq == 0.0

    # Test * with time on right
    node = BinaryOp(1, Literal(1, 2.0), "*", Identifier(1, "time"))
    state = ana.visit(node)
    assert state.is_time_dep
    assert state.freq == 2.0


def test_analyzer_function_call_defaults():
    ana = SafetyAnalyzer()
    # Unknown function
    node = FunctionCall(1, "unknown", [Literal(1, 1.0)])
    state = ana.visit(node)
    assert not state.is_time_dep

    # Low freq sin
    node = FunctionCall(1, "sin", [Identifier(1, "time")])  # freq=1.0
    state = ana.visit(node)
    assert state.is_time_dep
    assert len(ana.events) == 0


def test_scan_file_io_error():
    events, meta, qual = scan_file_full("nonexistent_file.milk")
    assert events == []
    assert meta == {}
    assert qual.background_type == "Unknown"


def test_parse_metadata_error():
    code = "// Expect: RuleID=NotANumber"
    meta = parse_metadata(code)
    assert meta == {}


def test_scanner_main_execution(tmp_path, capsys):
    p = tmp_path / "test.milk"
    p.write_text("ob_r = 0.5;")

    # We need to import the module dynamically or use runpy to execute the main block
    import runpy

    # Mock sys.argv
    with patch.object(sys, "argv", ["vizscan/static.py", str(p)]):
        runpy.run_module("vizscan.static", run_name="__main__")

    captured = capsys.readouterr()
    # Should print nothing for safe file, or we can add a violation

    p.write_text("ob_r = 1 - ob_r;")  # BAN
    with patch.object(sys, "argv", ["vizscan/static.py", str(p)]):
        runpy.run_module("vizscan.static", run_name="__main__")
    captured = capsys.readouterr()
    assert "RiskLevel.BAN" in captured.out


def test_analyzer_visit_program_block():
    # Test that analyze() handles Program and Block nodes
    ana = SafetyAnalyzer()
    prog = Program(1, [Block(1, [Assignment(1, "x", Literal(1, 1.0))])])
    ana.analyze(prog)
    # Should not crash
    assert True


def test_parser_swizzling_loop():
    # Test x.y.z
    tokens = MilkLexer("v.x.y;").tokenize()
    parser = MilkParser(tokens)
    # We need to parse_term directly
    term = parser.parse_term()  # v.x.y

    assert isinstance(term, MemberAccess)
    assert term.member == "y"
    assert isinstance(term.expr, MemberAccess)
    assert term.expr.member == "x"


def test_analyzer_unknown_node():
    ana = SafetyAnalyzer()

    # Pass a node type that isn't handled explicitly
    class UnknownNode:
        pass

    state = ana.visit(UnknownNode())
    assert not state.is_time_dep


def test_parser_unexpected_token():
    tokens = MilkLexer("+").tokenize()
    parser = MilkParser(tokens)
    assert parser.parse_statement() is None


def test_empty_shader(tmp_path):
    p = tmp_path / "empty_shader.milk"
    p.write_text('warp_shader = "";')
    events, _, _ = scan_file_full(str(p))
    assert len(events) == 0


def test_parser_arg_list_variations():
    # Test empty args
    tokens = MilkLexer("f();").tokenize()
    parser = MilkParser(tokens)
    # parse_statement -> parse_expression? No, f() is expression.
    # We need to parse_term or parse_expression
    # But f() is FunctionCall.
    # parse_term handles ID -> LPAREN -> parse_arg_list

    # f()
    tokens = MilkLexer("f()").tokenize()
    parser = MilkParser(tokens)
    term = parser.parse_term()
    assert isinstance(term, FunctionCall)
    assert len(term.args) == 0

    # f(a, b)
    tokens = MilkLexer("f(a, b)").tokenize()
    parser = MilkParser(tokens)
    term = parser.parse_term()
    assert isinstance(term, FunctionCall)
    assert len(term.args) == 2


def test_quality_analyzer_scenarios():
    # 1. Dark Background
    qa = QualityAnalyzer()
    qa.visit_Assignment(Assignment(1, "ob_r", Literal(1, 0.0)))
    qa.visit_Assignment(Assignment(1, "ob_g", Literal(1, 0.0)))
    qa.visit_Assignment(Assignment(1, "ob_b", Literal(1, 0.0)))
    rep = qa.generate_report()
    assert rep.background_type == "Dark"

    # 2. Light Background
    qa = QualityAnalyzer()
    qa.visit_Assignment(Assignment(1, "ob_r", Literal(1, 1.0)))
    qa.visit_Assignment(Assignment(1, "ob_g", Literal(1, 1.0)))
    qa.visit_Assignment(Assignment(1, "ob_b", Literal(1, 1.0)))
    rep = qa.generate_report()
    assert rep.background_type == "Light"

    # 3. Medium Background
    qa = QualityAnalyzer()
    qa.visit_Assignment(Assignment(1, "ob_r", Literal(1, 0.5)))
    qa.visit_Assignment(Assignment(1, "ob_g", Literal(1, 0.5)))
    qa.visit_Assignment(Assignment(1, "ob_b", Literal(1, 0.5)))
    rep = qa.generate_report()
    assert rep.background_type == "Medium"

    # 4. Dynamic Background
    qa = QualityAnalyzer()
    qa.visit_Assignment(Assignment(1, "ob_r", Identifier(1, "time")))
    rep = qa.generate_report()
    assert rep.background_type == "Dynamic"

    # 5. Incomplete Background
    qa = QualityAnalyzer()
    qa.visit_Assignment(Assignment(1, "ob_r", Literal(1, 0.0)))
    rep = qa.generate_report()
    assert rep.background_type == "Unknown"


def test_scanner_main_quality_output(tmp_path, capsys):
    p = tmp_path / "test.milk"
    p.write_text("ob_r = 0.0; ob_g = 0.0; ob_b = 0.0;")

    import runpy

    with patch.object(sys, "argv", ["vizscan/static.py", str(p)]):
        runpy.run_module("vizscan.static", run_name="__main__")
    captured = capsys.readouterr()
    assert "Quality Report:" in captured.out
    assert "Dark Background" in captured.out


def test_quality_analyzer_nested_blocks():
    # Program -> Block -> Assignment
    qa = QualityAnalyzer()
    prog = Program(1, [Block(1, [Assignment(1, "ob_r", Literal(1, 0.0))])])
    qa.analyze(prog)
    assert qa.bg_color["r"] == 0.0


def test_extract_shaders_multiple():
    code = 'warp_shader = "w"; comp_shader = "c";'
    shaders = extract_shaders(code)
    assert shaders["warp"] == "w"
    assert shaders["comp"] == "c"


def test_scanner_main_invalid_file(capsys):
    import runpy

    with patch.object(sys, "argv", ["vizscan/static.py", "nonexistent.milk"]):
        runpy.run_module("vizscan.static", run_name="__main__")
    captured = capsys.readouterr()
    # Should print nothing or error? Code checks os.path.isfile
    assert captured.out == ""
