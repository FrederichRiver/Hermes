from utils import parser


def test_parse_sse_html():
    sample = """
    <html><body>
    <table>
      <tr><td>代码</td><td>名称</td></tr>
      <tr><td>600000</td><td>浦发银行</td></tr>
      <tr><td>600004</td><td>白云机场</td></tr>
    </table>
    </body></html>
    """
    res = parser.parse_sse_html(sample)
    assert "SH600000" in res
    assert "SH600004" in res


def test_parse_szse_html():
    sample = """
    <html><body>
    <ul>
      <li><a href="/stock/000001">000001 平安银行</a></li>
      <li><a href="/stock/000002">000002 万科A</a></li>
    </ul>
    </body></html>
    """
    res = parser.parse_szse_html(sample)
    assert "SZ000001" in res
    assert "SZ000002" in res
