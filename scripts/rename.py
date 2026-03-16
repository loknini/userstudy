import os
from tqdm import tqdm

emotion_list = [
    "amusement",
    "awe",
    "contentment",
    "excitement",
    "anger",
    "disgust",
    "fear",
    "sadness",
]
# Read the id2content dictionary from the TXT file
id2content_from_file = {}
with open("//VCC-EMO/results/id2content.txt", "r", encoding="utf-8") as txtfile:
    for line in txtfile:
        id, content = line.strip().split("\t", 1)
        id2content_from_file[int(id)] = content

print("id2content has been loaded from id2content.txt")
print(id2content_from_file)


target_dir = "//VCC-EMO/results"
dir_list = os.listdir(target_dir)

# print(dir_list)
for image_dir in tqdm(dir_list):
    if not os.path.isdir(os.path.join(target_dir, image_dir, "json")):
        continue
    file_dir = os.path.join(target_dir, image_dir, "json")
    # print(file_dir)
    for root, _, file_list in tqdm(os.walk(file_dir), leave=False):
        for file_name in file_list:
            if file_name.startswith("emo") or file_name.startswith("sd"):
                continue
            if file_name.endswith(".jpg") or file_name.endswith(".png"):
                content_id = int(file_name.split("-")[0])
                emotion = file_name.split("-")[1]
                if content_id in id2content_from_file and emotion in emotion_list:
                    # new_name = f"{content_id}-{id2content_from_file[content_id]}-{file_name}.png"
                    new_name = file_name.replace(
                        f"{str(content_id)}-{emotion}",
                        f"{str(content_id)}-{id2content_from_file[content_id]}-{emotion}",
                    )
                    old_path = os.path.join(root, file_name)
                    new_path = os.path.join(root, new_name)
                    os.rename(old_path, new_path)
                    # print(f"Renamed {old_path} to {new_path}")
