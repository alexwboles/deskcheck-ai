// Synthetic, offline standard-control app for native acceptance. No real data.
using System;
using System.Drawing;
using System.IO;
using System.Web.Script.Serialization;
using System.Windows.Forms;

public sealed class Fixture : Form {
    readonly TextBox input;
    readonly Label result;
    readonly string statePath;
    int clicks;
    Fixture(string path, bool decoy, bool mismatch) {
        statePath = path;
        Text = "DeskCheck Synthetic Fixture";
        ClientSize = new Size(640, 340);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(246, 249, 252);
        if (decoy) { Text="DeskCheck Decoy Fixture"; BackColor=Color.Magenta; TopMost=true; }
        Font = new Font("Segoe UI", 11);
        Controls.Add(new Label {Text="DeskCheck Sample",Location=new Point(24,24),Size=new Size(580,32),Font=new Font("Segoe UI",16,FontStyle.Bold)});
        Controls.Add(new Label {Text="Note",Location=new Point(24,64),Size=new Size(580,22)});
        input = new TextBox {Name="SyntheticInput",Location=new Point(24,88),Size=new Size(540,32),TabIndex=0};
        var button = new Button {Text="Mark complete",Location=new Point(24,145),Size=new Size(180,42),TabIndex=1};
        result = new Label {Text="Waiting for a synthetic test",Location=new Point(24,210),Size=new Size(580,66)};
        Controls.Add(input); Controls.Add(button); Controls.Add(result);
        Controls.Add(new Label {Text="Offline fixture only. No customer records or network access.",Location=new Point(24,300),Size=new Size(590,28)});
        input.TextChanged += delegate { Save(); };
        button.Click += delegate { clicks++; result.Text=mismatch ? "Saved: Draft note" : "Saved: "+input.Text; Save(); };
        Shown += delegate {Save();};
    }
    void Save() {
        if (!String.IsNullOrEmpty(statePath))
            File.WriteAllText(statePath,new JavaScriptSerializer().Serialize(new {text=input.Text,clicks=clicks,result=result.Text}));
    }
    [STAThread] public static void Main(string[] args) {
        Application.EnableVisualStyles();
        Application.Run(new Fixture(args.Length>0?args[0]:null,args.Length>1&&args[1]=="decoy",args.Length>1&&args[1]=="mismatch"));
    }
}
