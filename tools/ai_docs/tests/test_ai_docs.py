#!/usr/bin/env python3
"""
Test suite for the AI-Native Dev Stack tooling.

Zero-dependency (stdlib unittest only) so CI needs no `pip install`:
    python -m unittest discover -s tools/ai_docs/tests

Covers the pure, stateless functions the methodology says to test first
(parsers, LOC counter, module discovery) plus regression tests for bugs
fixed during the repo review.
"""

import sys
import tempfile
import unittest
from pathlib import Path

# Make the tools/ai_docs/ modules importable regardless of cwd.
_TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TOOLS_DIR))

import source_exts                          # noqa: E402
import generate_ai_summary as gen           # noqa: E402
import assemble_context as asm              # noqa: E402
import generate_metrics as met              # noqa: E402
import update_on_edit as upd                # noqa: E402


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# source_exts — single source of truth
# ---------------------------------------------------------------------------
class TestSourceExts(unittest.TestCase):
    def test_common_extensions_present(self):
        for ext in (".py", ".rs", ".ts", ".cpp", ".h", ".go", ".java", ".cs"):
            self.assertIn(ext, source_exts.ALL_SOURCE_EXTS)

    def test_hxx_present_everywhere(self):
        # Regression: .hxx used to be parsed by one tool but ignored by others.
        self.assertIn(".hxx", source_exts.ALL_SOURCE_EXTS)
        self.assertIn(".hxx", source_exts.CPP_EXTS)

    def test_all_is_union_of_language_sets(self):
        union = (
            source_exts.CPP_EXTS | source_exts.RUST_EXTS | source_exts.TS_EXTS |
            source_exts.JS_EXTS | source_exts.PYTHON_EXTS | source_exts.GO_EXTS |
            source_exts.JAVA_EXTS | source_exts.KOTLIN_EXTS | source_exts.CS_EXTS |
            source_exts.FS_EXTS | source_exts.SWIFT_EXTS | source_exts.RUBY_EXTS |
            source_exts.PHP_EXTS
        )
        self.assertEqual(union, source_exts.ALL_SOURCE_EXTS)

    def test_tools_share_the_same_set(self):
        # The whole point of source_exts: no divergent copies.
        self.assertIs(upd.WATCHED_EXTENSIONS, source_exts.ALL_SOURCE_EXTS)
        self.assertIs(met.SOURCE_EXTENSIONS, source_exts.ALL_SOURCE_EXTS)


# ---------------------------------------------------------------------------
# generate_ai_summary — LOC counter
# ---------------------------------------------------------------------------
class TestCountLoc(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_blank_and_line_comments_excluded(self):
        f = _write(self.tmp / "a.py", "def foo():\n    # comment\n    return 1\n\n")
        self.assertEqual(gen.count_loc(f), 2)

    def test_c_block_comment_excluded(self):
        f = _write(self.tmp / "b.cpp", "/* line1\nline2 */\ncode();\n")
        self.assertEqual(gen.count_loc(f), 1)

    def test_missing_file_returns_zero(self):
        self.assertEqual(gen.count_loc(self.tmp / "nope.py"), 0)


# ---------------------------------------------------------------------------
# generate_ai_summary — language parsers
# ---------------------------------------------------------------------------
class TestParsers(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_parse_rust(self):
        f = _write(self.tmp / "lib.rs",
                   "pub struct Foo;\n"
                   "pub enum Bar { A, B }\n"
                   "pub fn hello() {}\n"
                   "pub trait Greet {}\n"
                   '#[no_mangle]\npub extern "C" fn c_entry() {}\n')
        r = gen.parse_rust(f)
        self.assertIn("Foo", r["pub_structs"])
        self.assertIn("Bar", r["pub_enums"])
        self.assertIn("hello", r["pub_fns"])
        self.assertIn("Greet", r["pub_traits"])
        self.assertIn("c_entry", r["extern_c_fns"])

    def test_parse_python(self):
        f = _write(self.tmp / "m.py",
                   "@dataclass\nclass Config:\n    x: int\n"
                   "class Service:\n    pass\n"
                   "def do_thing():\n    pass\n")
        r = gen.parse_python(f)
        self.assertIn("Config", r["dataclasses"])
        self.assertIn("Service", r["classes"])
        self.assertIn("do_thing", r["public_functions"])

    def test_parse_typescript(self):
        f = _write(self.tmp / "m.ts",
                   "export class Widget {}\n"
                   "export interface Props {}\n"
                   "export function render() {}\n")
        r = gen.parse_typescript(f)
        self.assertIn("Widget", r["classes"])
        self.assertIn("Props", r["interfaces"])
        self.assertIn("render", r["exported_functions"])

    def test_parse_cpp_host_struct_split(self):
        f = _write(self.tmp / "m.h",
                   "struct PanelHost {};\n"
                   "struct PlainData {};\n"
                   "class Manager {};\n")
        r = gen.parse_cpp(f)
        self.assertIn("PanelHost", r["host_structs"])
        self.assertIn("PlainData", r["structs"])
        self.assertIn("Manager", r["classes"])


# ---------------------------------------------------------------------------
# generate_ai_summary — end-to-end summary
# ---------------------------------------------------------------------------
class TestGenerateSummary(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_summary_has_loc_table_and_purpose(self):
        _write(self.tmp / "AI_CONTEXT.md", "## Purpose\nDoes a thing.\n## Forbidden\n- nope\n")
        _write(self.tmp / "lib.rs", "pub fn hello() {}\n")
        out = gen.generate_summary(self.tmp)
        self.assertIn("## Files & LOC", out)
        self.assertIn("Does a thing.", out)
        self.assertIn("hello()", out)

    def test_oversized_flag(self):
        _write(self.tmp / "AI_CONTEXT.md", "## Purpose\nBig.\n")
        _write(self.tmp / "big.py", "x = 1\n" * 1600)
        out = gen.generate_summary(self.tmp)
        self.assertIn("🔴", out)


# ---------------------------------------------------------------------------
# assemble_context — pure helpers
# ---------------------------------------------------------------------------
class TestAssembleHelpers(unittest.TestCase):
    def test_has_rt_constraints(self):
        self.assertTrue(asm.has_rt_constraints("Runs on the audio thread, zero alloc."))
        self.assertFalse(asm.has_rt_constraints("A plain config module."))

    def test_extract_adr_refs_zero_pads_and_dedups(self):
        # Contract: only 3-4 digit refs match (\d{3,4}); they are zero-padded to
        # 4 digits and deduplicated. Refs outside the "## See also" section are
        # ignored. NOTE: a 1-2 digit ref like "ADR-7" is intentionally NOT
        # matched — the methodology mandates 4-digit ADR ids (docs/adr/NNNN-*).
        ctx = (
            "## Purpose\nx\n"
            "## See also\n"
            "- ADR-7: one-digit ref, NOT matched\n"
            "- ADR-004: three-digit, padded to 0004\n"
            "- ADR-0004: duplicate of the above\n"
            "- ADR-1234: four-digit\n"
            "## Next\n- ADR-555: outside section, ignored\n"
        )
        refs = asm.extract_adr_refs(ctx)
        self.assertEqual(refs, ["ADR-0004", "ADR-1234"])

    def test_find_module_walks_up_to_ai_context(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()                       # stop boundary
            mod = root / "src" / "auth"
            _write(mod / "AI_CONTEXT.md", "## Purpose\nx\n")
            src = _write(mod / "deep" / "Token.rs", "pub fn t() {}\n")
            self.assertEqual(asm.find_module(src), mod)

    def test_find_module_returns_none_without_context(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            src = _write(root / "src" / "a.py", "x = 1\n")
            self.assertIsNone(asm.find_module(src))

    def test_graphify_explain_returns_none_without_graph(self):
        # Regression: the assembler must not invoke graphify (or emit a section)
        # when there is no graph.json. The guard runs before any subprocess, so
        # this holds whether or not the graphify binary is installed.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src = _write(root / "src" / "a.rs", "pub fn f() {}\n")
            self.assertIsNone(asm.run_graphify_explain("graphify", root, src))


# ---------------------------------------------------------------------------
# generate_metrics — coverage discovery (regression for SKIP_DIRS bug)
# ---------------------------------------------------------------------------
class TestMetricsDiscovery(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_skip_dirs_has_no_file_names(self):
        # Regression: listing "AI_CONTEXT.md"/"AI_SUMMARY.md" (file names) in
        # SKIP_DIRS made every module exclude itself → coverage stuck at 0%.
        self.assertNotIn("AI_CONTEXT.md", met.SKIP_DIRS)
        self.assertNotIn("AI_SUMMARY.md", met.SKIP_DIRS)

    def test_find_context_modules_finds_module(self):
        mod = self.root / "src" / "auth"
        _write(mod / "AI_CONTEXT.md", "## Purpose\nx\n")
        _write(mod / "a.py", "x = 1\n")
        found = met.find_context_modules(self.root)
        self.assertIn(mod, found)

    def test_find_context_modules_skips_noise_dirs(self):
        _write(self.root / "node_modules" / "pkg" / "AI_CONTEXT.md", "## Purpose\nx\n")
        self.assertEqual(met.find_context_modules(self.root), [])

    def test_coverage_is_100_percent_when_all_covered(self):
        mod = self.root / "src"
        _write(mod / "AI_CONTEXT.md", "## Purpose\nx\n")
        _write(mod / "a.py", "x = 1\n")
        source_dirs = met.find_source_dirs(self.root)
        covered = met.find_context_modules(self.root)
        self.assertEqual(len(source_dirs), len(covered))

    def test_is_summary_stale_when_missing(self):
        mod = self.root / "src"
        _write(mod / "a.py", "x = 1\n")
        self.assertTrue(met.is_summary_stale(mod))

    def test_count_kfp_and_adrs(self):
        _write(self.root / "docs" / "KNOWN_FAILURE_PATTERNS.md",
               "# KFP\n### 1.1 One\nbody\n### 1.2 Two\nbody\n")
        _write(self.root / "docs" / "adr" / "0001-first.md", "# ADR-0001\n")
        _write(self.root / "docs" / "adr" / "README.md", "# index\n")
        self.assertEqual(met.count_kfp_patterns(self.root), 2)
        self.assertEqual(met.count_adrs(self.root), 1)  # README excluded


# ---------------------------------------------------------------------------
# update_on_edit — module discovery mirrors assemble_context
# ---------------------------------------------------------------------------
class TestUpdateOnEdit(unittest.TestCase):
    def test_find_module(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            mod = root / "mod"
            _write(mod / "AI_CONTEXT.md", "## Purpose\nx\n")
            src = _write(mod / "a.py", "x = 1\n")
            self.assertEqual(upd.find_module(str(src)), mod)


if __name__ == "__main__":
    unittest.main(verbosity=2)
