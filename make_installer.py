import os
import subprocess
import shutil

appname = "snapsync"

def main():
    # Run PyInstaller command
    subprocess.run(["pyinstaller", "--onefile", "--name", appname, "src/{}.py".format(appname),
                    "--icon=icon.ico", "--noconsole", "--add-data", "icon.ico:."])

    # Delete the existing snapsync.exe file
    if os.path.exists(f"./{appname}.exe"):
        os.remove(f"./{appname}.exe")

    # Move the snapsync.exe file from ./dist/ to the current directory
    if os.path.exists(f"./dist/{appname}.exe"):
        os.replace(f"./dist/{appname}.exe", f"./{appname}.exe")

    # Delete the ./build/ directory
    if os.path.exists("./build"):
        shutil.rmtree("./build")

    # Delete the ./dist/ directory
    if os.path.exists("./dist"):
        shutil.rmtree("./dist")

    # Delete the snapsync.spec file
    if os.path.exists(f"./{appname}.spec"):
        os.remove(f"./{appname}.spec")
    
    # call inno setup
    subprocess.run(["C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe", "main.iss"])


if __name__ == "__main__":
    main()
