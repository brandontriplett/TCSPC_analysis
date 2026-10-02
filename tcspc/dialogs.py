"""Optional tkinter pickers used by the scripts when no path is given."""


def pick_files(title="Select TCSPC CSV file(s)"):
    import tkinter as tk
    from tkinter import filedialog
    from pathlib import Path

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askopenfilenames(
        title=title,
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
    )
    root.destroy()
    return [Path(p) for p in selected]


def pick_folder(title="Select Folder Containing TCSPC CSVs"):
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askdirectory(title=title)
    root.destroy()
    return selected or None
