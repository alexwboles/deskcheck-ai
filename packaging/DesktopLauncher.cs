using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

static class DesktopLauncher {
    [STAThread] static void Main() {
        string exe=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"DeskCheck.exe");
        if (!File.Exists(exe)) {
            MessageBox.Show("DeskCheck.exe is missing. Extract the entire ZIP into one folder, then try again.","DeskCheck");
            return;
        }
        try {
            Process.Start(new ProcessStartInfo(exe,"gui") {UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=AppDomain.CurrentDomain.BaseDirectory});
        } catch (Exception) {
            MessageBox.Show("Could not start DeskCheck. Check that the entire ZIP was extracted and that your organization permits unsigned local applications. Do not bypass security warnings.","DeskCheck");
        }
    }
}
