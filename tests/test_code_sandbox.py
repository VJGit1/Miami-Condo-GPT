"""Unit tests for dynamic code execution security scanner and HTML extraction."""

import os
import re
import unittest
from main import GENERATED_DIR, detect_malicious_code, execute_generated_pdf, extract_and_remove_html


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
        self.assertIn("Here is the report:", stripped_text)
        self.assertNotIn("PDF Generated", stripped_text)
        self.assertNotIn("PDF generated", stripped_text)

    def test_extract_html_chart_block(self):
        text = "Here is the chart:\n```html\n<canvas id='myChart'></canvas>\n```"
        html_block, stripped_text, code = extract_and_remove_html(text)
        self.assertIsNone(code)
        self.assertIsNotNone(html_block)
        self.assertIn("<canvas id='myChart'></canvas>", str(html_block))

    def test_pdf_failure_does_not_claim_success(self):
        message = str(execute_generated_pdf("print('hello')"))
        self.assertIn("did not write a PDF file", message)
        self.assertNotIn("Download PDF", message)

    def test_blocked_pdf_code_does_not_claim_success(self):
        message = str(execute_generated_pdf("import os\nos.system('echo hi')"))
        self.assertIn("blocked", message.lower())
        self.assertNotIn("Download PDF", message)

    def test_pdf_success_writes_unique_download(self):
        code = """
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
c = canvas.Canvas('report.pdf', pagesize=letter)
c.drawString(100, 750, 'Miami Condo Report')
c.save()
"""
        message = str(execute_generated_pdf(code))
        match = re.search(r'href="/downloads/([0-9a-f]{32}\.pdf)"', message)
        self.assertIsNotNone(match)
        self.assertNotIn("report.pdf", message)
        path = os.path.join(GENERATED_DIR, match.group(1))
        self.addCleanup(lambda: os.path.isfile(path) and os.remove(path))
        self.assertTrue(os.path.isfile(path))


if __name__ == "__main__":
    unittest.main()
