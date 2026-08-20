import av
import os
from PIL import Image


def resize_to_fixed_resolution(img, target_size=(512, 512)):
    return img.resize(target_size, Image.LANCZOS)


def extract_frames_cover_whole_video(video_path, output_dir, max_frames=12, output_size=(512, 512)):
    """
    优先提取关键帧，不足部分均匀补帧，确保覆盖视频全时长（起始+末尾），所有帧统一缩放
    """
    os.makedirs(output_dir, exist_ok=True)
    container = av.open(video_path)
    stream = container.streams.video[0]

    all_frames = []
    key_frames = []
    pts_set = set()

    print(f"🚀 处理视频：{os.path.basename(video_path)}")

    # === 解码所有帧，记录关键帧和全部帧 ===
    for packet in container.demux(stream):
        for frame in packet.decode():
            all_frames.append(frame)
            if frame.key_frame:
                key_frames.append(frame)

    total_frames = len(all_frames)
    print(f"🎞 总帧数: {total_frames}, 关键帧数: {len(key_frames)}")

    saved = 0

    # === 第一步：保存前 max_frames 个关键帧（按顺序）===
    for frame in key_frames:
        if saved >= max_frames:
            break
        img = resize_to_fixed_resolution(frame.to_image(), output_size)
        img.save(os.path.join(output_dir, f"frame_{saved:03d}.jpg"))
        pts_set.add(frame.pts)
        saved += 1

    # === 第二步：按时间均匀补帧，覆盖整个视频段 ===
    remaining = max_frames - saved
    if remaining > 0:
        # 均匀取 remaining 个索引，含第一帧和最后一帧
        sample_indices = [round(i * (total_frames - 1) / (remaining + 1)) for i in range(1, remaining + 1)]

        for idx in sample_indices:
            if saved >= max_frames:
                break
            frame = all_frames[idx]
            if frame.pts not in pts_set:
                img = resize_to_fixed_resolution(frame.to_image(), output_size)
                img.save(os.path.join(output_dir, f"frame_{saved:03d}.jpg"))
                pts_set.add(frame.pts)
                saved += 1

    container.close()
    print(f"✅ 共保存帧: {saved}（目标: {max_frames}），覆盖全视频，尺寸: {output_size[0]}x{output_size[1]}")


# ✅ 用法示例
if __name__ == "__main__":
    extract_frames_cover_whole_video(
        video_path=r"E:\你的路径\video.mp4",  # ← 你的源视频路径
        output_dir=r"E:\你的路径\frames",  # ← 输出目录
        max_frames=12,
        output_size=(512, 512)
    )
