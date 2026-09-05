using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

[assembly: AssemblyTitle("剪辑智能包装")]
[assembly: AssemblyProduct("剪辑智能包装")]
[assembly: AssemblyDescription("本地视频剪辑、字幕与音效包装桌面软件")]
[assembly: AssemblyVersion("1.0.0.0")]

internal static class Program
{
    internal static readonly string Root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
    internal static readonly string Data = Path.Combine(Root, "data");
    internal static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
    internal static EventWaitHandle ActivateEvent;
    static readonly object LogLock = new object();

    [STAThread]
    static void Main()
    {
        Directory.CreateDirectory(Path.Combine(Data, "logs"));
        Directory.CreateDirectory(Path.Combine(Data, "temp"));
        Environment.SetEnvironmentVariable("TEMP", Path.Combine(Data, "temp"));
        Environment.SetEnvironmentVariable("TMP", Path.Combine(Data, "temp"));
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        string key;
        using (var sha = SHA256.Create())
            key = BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(Root.ToLowerInvariant()))).Replace("-", "").Substring(0, 20);
        bool created;
        using (ActivateEvent = new EventWaitHandle(false, EventResetMode.AutoReset, "Local\\SmartVideoPackaging.Activate." + key))
        using (var mutex = new Mutex(true, "Local\\SmartVideoPackaging.Desktop." + key, out created))
        {
            if (!created) { ActivateEvent.Set(); Log("Activated existing desktop window."); return; }
            Application.ThreadException += delegate(object sender, ThreadExceptionEventArgs e) { Log(e.Exception.ToString()); MessageBox.Show(e.Exception.Message, "剪辑智能包装"); };
            try { Application.Run(new EditorWindow()); }
            catch (Exception e) { Log(e.ToString()); MessageBox.Show("软件无法启动：\n" + e.Message + "\n\n日志：" + Path.Combine(Data, "logs", "desktop.log"), "剪辑智能包装", MessageBoxButtons.OK, MessageBoxIcon.Error); }
        }
    }

    internal static void Log(string message)
    {
        try { lock (LogLock) File.AppendAllText(Path.Combine(Data, "logs", "desktop.log"), DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + message + Environment.NewLine, Encoding.UTF8); }
        catch { }
    }
}

internal sealed class EditorWindow : Form
{
    const string AppUrl = "http://127.0.0.1:8765/";
    readonly Panel splash = new Panel();
    readonly Label detail = new Label();
    readonly Button retry = new Button();
    readonly HttpClient http = new HttpClient(new HttpClientHandler { UseProxy = false });
    readonly string boundsFile = Path.Combine(Program.Data, "desktop-window.json");
    WebView2 web;
    RegisteredWaitHandle activationWait;
    bool starting, ready, closing, allowClose;

    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

    internal EditorWindow()
    {
        Text = "剪辑智能包装";
        Name = "SmartVideoPackagingDesktop";
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        BackColor = Color.FromArgb(17, 19, 23);
        ForeColor = Color.FromArgb(231, 233, 239);
        Font = new Font("Microsoft YaHei UI", 10);
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(1360, 820);
        MinimumSize = new Size(1100, 700);
        WindowState = FormWindowState.Maximized;
        RestoreBoundsFromDisk();
        http.Timeout = TimeSpan.FromSeconds(2);

        splash.Dock = DockStyle.Fill;
        var stack = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 5, Padding = new Padding(70) };
        stack.RowStyles.Add(new RowStyle(SizeType.Percent, 45));
        stack.RowStyles.Add(new RowStyle(SizeType.Absolute, 64));
        stack.RowStyles.Add(new RowStyle(SizeType.Absolute, 100));
        stack.RowStyles.Add(new RowStyle(SizeType.Absolute, 50));
        stack.RowStyles.Add(new RowStyle(SizeType.Percent, 55));
        var title = new Label { Text = "剪辑智能包装", Font = new Font("Microsoft YaHei UI", 26, FontStyle.Bold), Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleCenter };
        detail.Text = "正在启动本地剪辑服务…";
        detail.Dock = DockStyle.Fill;
        detail.TextAlign = ContentAlignment.MiddleCenter;
        detail.ForeColor = Color.FromArgb(161, 169, 184);
        retry.Text = "重新连接";
        retry.Size = new Size(130, 38);
        retry.Anchor = AnchorStyles.None;
        retry.FlatStyle = FlatStyle.Flat;
        retry.BackColor = Color.FromArgb(48, 212, 192);
        retry.ForeColor = Color.Black;
        retry.Visible = false;
        retry.Click += async delegate { await StartEditor(); };
        stack.Controls.Add(title, 0, 1); stack.Controls.Add(detail, 0, 2); stack.Controls.Add(retry, 0, 3);
        splash.Controls.Add(stack); Controls.Add(splash);

        Shown += async delegate {
            int dark = 1;
            try { DwmSetWindowAttribute(Handle, 20, ref dark, sizeof(int)); } catch { }
            activationWait = ThreadPool.RegisterWaitForSingleObject(Program.ActivateEvent, delegate(object state, bool timeout) {
                if (IsDisposed || !IsHandleCreated) return;
                try { BeginInvoke((Action)delegate { if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal; Show(); Activate(); BringToFront(); }); } catch { }
            }, null, Timeout.Infinite, false);
            await StartEditor();
        };
        FormClosing += OnClosing;
        FormClosed += delegate {
            SaveBoundsToDisk();
            if (activationWait != null) activationWait.Unregister(null);
            if (web != null) web.Dispose();
            http.Dispose();
            // The API is shared with browser editors; leave active jobs intact.
            Program.Log("Desktop closed; shared local service retained.");
        };
    }

    async Task<bool> ServerReady()
    {
        HttpResponseMessage response;
        try { response = await http.GetAsync(AppUrl + "api/desktop-health"); }
        catch (HttpRequestException) { return false; }
        catch (TaskCanceledException) { return false; }
        using (response)
        {
            if (!response.IsSuccessStatusCode) throw new InvalidOperationException("8765 端口上已有其他服务或旧版服务。请关闭旧版启动的服务后重新打开软件。");
            Dictionary<string, object> health;
            try { health = Program.Json.Deserialize<Dictionary<string, object>>(await response.Content.ReadAsStringAsync()); }
            catch { throw new InvalidOperationException("本地服务响应不正确，请检查 data\\logs 中的日志。"); }
            if (!health.ContainsKey("application") || (string)health["application"] != "smart-video-packaging" ||
                !health.ContainsKey("root") || !string.Equals(Path.GetFullPath((string)health["root"]).TrimEnd('\\', '/'), Program.Root, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("8765 端口正由另一个程序目录使用。请先关闭另一份剪辑智能包装。");
            return true;
        }
    }

    async Task StartEditor()
    {
        if (starting) return;
        starting = true; ready = false; splash.Visible = true; splash.BringToFront(); retry.Visible = false;
        try
        {
            detail.Text = "正在连接本地剪辑服务…";
            if (!await ServerReady())
            {
                string python = Path.Combine(Program.Root, ".venv", "Scripts", "pythonw.exe");
                if (!File.Exists(python) || !File.Exists(Path.Combine(Program.Root, "app.py")))
                    throw new FileNotFoundException("运行环境不完整，请先运行软件目录中的“安装运行环境.bat”。");
                var start = new ProcessStartInfo(python, "\"" + Path.Combine(Program.Root, "desktop", "backend.py") + "\"") {
                    WorkingDirectory = Program.Root, UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden
                };
                start.EnvironmentVariables["PYTHONUTF8"] = "1";
                start.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
                using (var process = Process.Start(start)) { Program.Log("Started local backend launcher PID " + process.Id); }
                bool serverReady = false;
                for (int attempt = 0; attempt < 90 && !IsDisposed; attempt++)
                {
                    await Task.Delay(500);
                    if (await ServerReady()) { serverReady = true; break; }
                }
                if (!serverReady) throw new TimeoutException("本地服务尚未启动。请查看 data\\logs\\server-error.log 后重试。");
            }
            if (IsDisposed) return;
            detail.Text = "正在打开剪辑工作台…";
            if (web == null)
            {
                CoreWebView2Environment.SetLoaderDllFolderPath(Path.Combine(Program.Root, "desktop", "native"));
                try { CoreWebView2Environment.GetAvailableBrowserVersionString(); }
                catch (WebView2RuntimeNotFoundException) { throw new InvalidOperationException("缺少 Microsoft Edge WebView2 Runtime，请从微软官网安装后重新打开。https://developer.microsoft.com/microsoft-edge/webview2/"); }
                string cache = Path.Combine(Program.Data, "desktop-webview");
                Directory.CreateDirectory(cache);
                var options = new CoreWebView2EnvironmentOptions("--autoplay-policy=no-user-gesture-required --disk-cache-size=67108864");
                var environment = await CoreWebView2Environment.CreateAsync(null, cache, options);
                web = new WebView2 { Dock = DockStyle.Fill, DefaultBackgroundColor = BackColor };
                Controls.Add(web); splash.BringToFront();
                await web.EnsureCoreWebView2Async(environment);
                web.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
                web.CoreWebView2.Settings.AreDevToolsEnabled = false;
                web.CoreWebView2.Settings.AreBrowserAcceleratorKeysEnabled = false;
                web.CoreWebView2.Settings.IsStatusBarEnabled = false;
                web.CoreWebView2.Settings.IsZoomControlEnabled = false;
                web.CoreWebView2.Settings.IsSwipeNavigationEnabled = false;
                web.CoreWebView2.NavigationStarting += delegate(object sender, CoreWebView2NavigationStartingEventArgs e) {
                    Uri uri;
                    if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out uri) || uri.GetLeftPart(UriPartial.Authority) != AppUrl.TrimEnd('/')) e.Cancel = true;
                };
                web.CoreWebView2.NewWindowRequested += delegate(object sender, CoreWebView2NewWindowRequestedEventArgs e) {
                    e.Handled = true;
                    Uri uri;
                    if (e.IsUserInitiated && Uri.TryCreate(e.Uri, UriKind.Absolute, out uri) && (uri.Scheme == "https" || uri.Scheme == "http"))
                        Process.Start(new ProcessStartInfo(e.Uri) { UseShellExecute = true });
                };
                web.CoreWebView2.NavigationCompleted += delegate(object sender, CoreWebView2NavigationCompletedEventArgs e) {
                    if (e.IsSuccess) { ready = true; splash.Visible = false; web.BringToFront(); web.Focus(); Program.Log("Editor ready; WebView2 " + environment.BrowserVersionString); }
                    else { ShowFailure("工作台连接失败：" + e.WebErrorStatus + "。请点击重新连接。"); }
                };
                web.CoreWebView2.WebMessageReceived += delegate(object sender, CoreWebView2WebMessageReceivedEventArgs e) {
                    if (!e.Source.StartsWith(AppUrl, StringComparison.Ordinal)) return;
                    try {
                        var message = Program.Json.Deserialize<Dictionary<string, object>>(e.WebMessageAsJson);
                        if (message.ContainsKey("type") && (string)message["type"] == "title" && message.ContainsKey("title")) {
                            string title = (string)message["title"]; Text = title.Substring(0, Math.Min(200, title.Length));
                        }
                    } catch { }
                };
                web.CoreWebView2.ProcessFailed += delegate(object sender, CoreWebView2ProcessFailedEventArgs e) {
                    Program.Log("WebView process failure: " + e.ProcessFailedKind);
                    if (e.ProcessFailedKind == CoreWebView2ProcessFailedKind.BrowserProcessExited || e.ProcessFailedKind == CoreWebView2ProcessFailedKind.RenderProcessExited) {
                        ready = false; web.Dispose(); web = null;
                        ShowFailure("工作台意外停止。点击重新连接，可以重新载入已保存的工程。");
                    }
                };
            }
            web.CoreWebView2.Navigate(AppUrl);
        }
        catch (Exception e) { Program.Log(e.ToString()); if (web != null && web.CoreWebView2 == null) { web.Dispose(); web = null; } ShowFailure(e.Message); }
        finally { starting = false; }
    }

    void ShowFailure(string message)
    {
        if (IsDisposed) return;
        detail.Text = message; retry.Visible = true; splash.Visible = true; splash.BringToFront();
    }

    async void OnClosing(object sender, FormClosingEventArgs e)
    {
        if (allowClose || !ready || web == null) return;
        e.Cancel = true;
        if (closing) return;
        closing = true;
        try
        {
            bool english = await web.ExecuteScriptAsync("typeof UI !== 'undefined' && UI.language === 'en'") == "true";
            bool dirty = await web.ExecuteScriptAsync("Boolean(window.DesktopShell && DesktopShell.hasUnsavedChanges())") == "true";
            if (dirty)
            {
                var decision = MessageBox.Show(this, english ? "Save changes before closing?\nYes: save and close. No: discard changes. Cancel: keep editing." : "关闭前要保存修改吗？\n是：保存并关闭；否：放弃本次修改；取消：继续编辑。", english ? "Unsaved changes" : "工程尚未保存", MessageBoxButtons.YesNoCancel, MessageBoxIcon.Question);
                if (decision == DialogResult.Cancel) return;
                if (decision == DialogResult.Yes)
                {
                    // ExecuteScriptAsync returns Promises as empty objects. Resolve via a
                    // temporary result flag so closing waits for the actual HTTP save.
                    await web.ExecuteScriptAsync("window.__desktopSaveResult=null; DesktopShell.saveForClose().then(ok=>{window.__desktopSaveResult=ok}).catch(()=>{window.__desktopSaveResult=false})");
                    string saved = "null";
                    for (int i = 0; i < 120 && saved == "null"; i++) { await Task.Delay(250); saved = await web.ExecuteScriptAsync("window.__desktopSaveResult"); }
                    if (saved != "true") { MessageBox.Show(this, english ? "The project could not be saved. The editor will stay open." : "工程尚未保存成功，窗口会保持打开。请检查提示后重试。", Text); return; }
                }
            }
            allowClose = true;
            BeginInvoke((Action)Close);
        }
        catch (Exception error) {
            Program.Log(error.ToString());
            if (MessageBox.Show(this, "无法检查保存状态。仍然关闭窗口吗？", "剪辑智能包装", MessageBoxButtons.YesNo, MessageBoxIcon.Warning) == DialogResult.Yes) { allowClose = true; BeginInvoke((Action)Close); }
        }
        finally { closing = false; }
    }

    void RestoreBoundsFromDisk()
    {
        try {
            if (!File.Exists(boundsFile)) return;
            var saved = Program.Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(boundsFile));
            var bounds = new Rectangle(Convert.ToInt32(saved["x"]), Convert.ToInt32(saved["y"]), Math.Max(1100, Convert.ToInt32(saved["width"])), Math.Max(700, Convert.ToInt32(saved["height"])));
            foreach (var screen in Screen.AllScreens) if (Rectangle.Intersect(screen.WorkingArea, bounds).Width >= 250 && Rectangle.Intersect(screen.WorkingArea, bounds).Height >= 150) { StartPosition = FormStartPosition.Manual; Bounds = bounds; break; }
            WindowState = Convert.ToBoolean(saved["maximized"]) ? FormWindowState.Maximized : FormWindowState.Normal;
        } catch { }
    }

    void SaveBoundsToDisk()
    {
        try {
            var bounds = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
            File.WriteAllText(boundsFile, Program.Json.Serialize(new { x = bounds.X, y = bounds.Y, width = bounds.Width, height = bounds.Height, maximized = WindowState == FormWindowState.Maximized }), Encoding.UTF8);
        } catch { }
    }
}
