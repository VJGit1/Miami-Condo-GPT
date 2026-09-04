"""Unit tests for dynamic code execution security scanner and HTML extraction."""

import unittest
from main import detect_malicious_code, extract_and_remove_html


class TestCodeExecutionSandbox(unittest.TestCase):

    def test_detects_malicious_os_commands(self):
        malicious_samples = [
            "import os\nos.system('rm -rf /')",
            "import subprocess\nsubprocess.run(['ls', '-la'])",
            "eval('__import__(\"os\").system(\"whoami\")')",
            "import socket\ns = socket.socket()",
            "import shutil\nshutil.rmtree('/tmp')",
        ]
        for sample in malicious_samples:
            self.assertTrue(detect_malicious_code(sample), f"Should detect malicious code in: {sample}")

    def test_allows_safe_reportlab_code(self):
        safe_code = """
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
c = canvas.Canvas('report.pdf', pagesize=letter)
c.drawString(100, 750, 'Miami Condo Report')
c.save()
"""
        self.assertFalse(detect_malicious_code(safe_code))

    def test_extract_python_code_block(self):
        text = "Here is the report:\n```python\nprint('hello')\n```"
        html_block, stripped_text, code = extract_and_remove_html(text)
        self.assertEqual(code, "print('hello')")
        self.assertEqual(stripped_text, "PDF Generated!")

    def test_extract_html_chart_block(self):
        text = "Here is the chart:\n```html\n<canvas id='myChart'></canvas>\n```"
        html_block, stripped_text, code = extract_and_remove_html(text)
        self.assertIsNone(code)
        self.assertIsNotNone(html_block)
        self.assertIn("<canvas id='myChart'></canvas>", str(html_block))


if __name__ == "__main__":
    unittest.main()
