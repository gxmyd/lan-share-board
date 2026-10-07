using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

public static class Launcher
{
    [STAThread]
    public static int Main()
    {
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        string script = Path.Combine(dir, "share_server.py");
        if (!File.Exists(script))
        {
            MessageBox.Show("未找到同目录下的 share_server.py", "共享剪贴板", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        string py = FindPython();
        if (py == null)
        {
            MessageBox.Show("请先安装 Python 3 环境（python.org 下载，安装时勾选 Add to PATH），再重新运行。", "共享剪贴板", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return 1;
        }
        try
        {
            string arg = py == "py" ? "-3 \"" + script + "\"" : "\"" + script + "\"";
            Process.Start(new ProcessStartInfo
            {
                FileName = py,
                Arguments = arg,
                WorkingDirectory = dir,
                UseShellExecute = true
            });
        }
        catch (Exception ex)
        {
            MessageBox.Show("启动失败：" + ex.Message, "共享剪贴板", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        return 0;
    }

    static string FindPython()
    {
        foreach (string c in new string[] { "python", "python3", "py" })
        {
            try
            {
                string arg = c == "py" ? "-3 --version" : "--version";
                var psi = new ProcessStartInfo(c, arg)
                {
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                };
                using (var p = Process.Start(psi))
                {
                    if (p.WaitForExit(3000) && p.ExitCode == 0) return c;
                }
            }
            catch { }
        }
        return null;
    }
}