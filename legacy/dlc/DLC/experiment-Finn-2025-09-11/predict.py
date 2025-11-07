import deeplabcut

# Path to your config.yaml
config_path = r"C:\Users\Finn\Downloads\SLU\Fall_2025\CV_Zebrafish\DLC\experiment-Finn-2025-09-11\config.yaml"

# Run analysis (this creates prediction CSV + h5 files in the same folder as the video)
deeplabcut.analyze_videos(config_path, [
                          r"C:\Users\Finn\Downloads\SLU\Fall_2025\CV_Zebrafish\DLC\experiment-Finn-2025-09-11\videos\Zebrafish_data_2.mp4"], save_as_csv=True)
