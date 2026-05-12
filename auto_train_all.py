"""
YOLO11-SAFE 消融实验自动训练脚本
=================================
主创新点: P2 检测头 + SCAA 跨尺度注意力 + SGLA 尺度引导标签分配
副创新点: GhostConv 轻量化卷积
损失改进: SACIoU 尺度自适应 CIoU
类别均衡: cls_pw 逆频率加权 + Copy-Paste 增强

使用方法:
    conda activate yolo11
    python auto_train_all.py

消融矩阵:
    Table 1: 核心对比 (Exp01-04)
    Table 2: 主创新子模块消融 (Exp05-08)
    Table 3: 副创新消融 (Exp09-10)
    Table 4: 损失函数消融 (Exp11-12)
    Table 5: 完整方案 (Exp12)
    Table 6: 优化方案 (Exp13-14) — 修复类别不均衡 + GhostConv 不稳定
"""

import warnings
warnings.filterwarnings("ignore", category=UserWarning, message=".*deterministic.*")
import torch
from ultralytics import YOLO


def main():
    # =========================================================
    # 实验配置
    # =========================================================
    experiments = [
        # =====================================================
        # Table 1: 核心对比
        # =====================================================
        {
            "yaml": "ultralytics/cfg/models/11/yolo11.yaml",
            "name": "Exp01_Baseline",
            "desc": "原版 YOLO11n 基线",
        },
        # {
        #     "yaml": "ultralytics/cfg/models/11/yolo11-p2.yaml",
        #     "name": "Exp02_P2_Only",
        #     "desc": "仅 P2 检测头",
        # },
        # {
        #     "yaml": "ultralytics/cfg/models/11/yolo11-safe.yaml",
        #     "name": "Exp03_SAFE_P2_SCAA",
        #     "desc": "P2 + SCAA (主创新核心)",
        # },
        # {
        #     "yaml": "ultralytics/cfg/models/11/yolo11-safe.yaml",
        #     "name": "Exp04_SAFE_Full",
        #     "desc": "P2 + SCAA + SGLA (主创新完整)",
        #     "scale_aware_boost": 0.2,
        # },

        # =====================================================
        # Table 2: 主创新子模块消融
        # =====================================================
        {
            "yaml": "ultralytics/cfg/models/11/yolo11-scaa-only.yaml",
            "name": "Exp05_SCAA_Only",
            "desc": "仅 SCAA (无 P2)",
        },
        {
            "yaml": "ultralytics/cfg/models/11/yolo11.yaml",
            "name": "Exp06_SGLA_Only",
            "desc": "仅 SGLA (无结构改动)",
            "scale_aware_boost": 0.2,
        },
        # {
        #     "yaml": "ultralytics/cfg/models/11/yolo11-p2.yaml",
        #     "name": "Exp07_P2_SGLA",
        #     "desc": "P2 + SGLA (无 SCAA)",
        #     "scale_aware_boost": 0.2,
        # },

        # # =====================================================
        # # Table 3: 副创新消融
        # # =====================================================
        # {
        #     "yaml": "ultralytics/cfg/models/11/yolo11-ghost.yaml",
        #     "name": "Exp08_Ghost_Only",
        #     "desc": "仅 GhostConv 轻量化",
        # },
        # {
        #     "yaml": "ultralytics/cfg/models/11/yolo11-safe-ghost.yaml",
        #     "name": "Exp09_SAFE_Ghost",
        #     "desc": "主创新 + 副创新 (无 SACIoU)",
        # },

        # =====================================================
        # Table 4: 损失函数消融
        # =====================================================
        {
            "yaml": "ultralytics/cfg/models/11/yolo11.yaml",
            "name": "Exp10_SACIoU_Only",
            "desc": "仅 SACIoU 损失",
            "use_saciou": True,
            "saciou_lambda": 1.0,
        },
        # {
        #     "yaml": "ultralytics/cfg/models/11/yolo11-safe.yaml",
        #     "name": "Exp11_SAFE_SACIoU",
        #     "desc": "主创新 + SACIoU",
        #     "scale_aware_boost": 0.2,
        #     "use_saciou": True,
        #     "saciou_lambda": 1.0,
        # },

        # # =====================================================
        # # Table 5: 完整方案
        # # =====================================================
        # {
        #     "yaml": "ultralytics/cfg/models/11/yolo11-safe-ghost.yaml",
        #     "name": "Exp12_Full_SAFE_Ghost_SACIoU",
        #     "desc": "全部启用: P2+SCAA+SGLA+Ghost+SACIoU",
        #     "scale_aware_boost": 0.2,
        #     "use_saciou": True,
        #     "saciou_lambda": 1.0,
        # },

        # # =====================================================
        # # Table 6: 优化方案 (修复 Exp12 问题 + 类别均衡)
        # # =====================================================
        # {
        #     "yaml": "ultralytics/cfg/models/11/yolo11-safe.yaml",
        #     "name": "Exp13_SAFE_SGLA_SACIoU_ClassBalanced",
        #     "desc": "SAFE+SGLA+SACIoU(温和)+类别均衡+CopyPaste",
        #     "scale_aware_boost": 0.2,
        #     "use_saciou": True,
        #     "saciou_lambda": 1.0,
        #     "cls_pw": 0.3,
        #     "copy_paste": 0.15,
        # },
        # {
        #     "yaml": "ultralytics/cfg/models/11/yolo11-safe-ghost-neck.yaml",
        #     "name": "Exp14_SAFE_GhostNeck_SGLA_SACIoU_HighRes",
        #     "desc": "SAFE+Ghost(仅neck)+SGLA+SACIoU(温和)+高分辨率",
        #     "scale_aware_boost": 0.2,
        #     "use_saciou": True,
        #     "saciou_lambda": 1.0,
        #     "cls_pw": 0.3,
        #     "copy_paste": 0.15,
        #     "epochs": 200,
        #     "imgsz": 800,
        #     "batch": 16,  # 高分辨率需要更小 batch 防止 OOM
        # },
    ]

    # =========================================================
    # 公共训练参数 (根据你的数据集修改)
    # =========================================================
    common_kwargs = dict(
        # --- 数据集 ---
        data="EVD4UAV.yaml",       # 修改为你的数据集 yaml
        imgsz=640,
        batch=32,
        project="/home/ssssss/1yolo/Ablation_Results",
        device=0,
        workers=8,
        val=True,
        plots=True,
        save=True,
        amp=True,
        cache=False,

        # --- 优化器 ---
        optimizer="AdamW",
        lr0=0.001,
        lrf=0.01,
        momentum=0.937,
        weight_decay=0.0005,
        cos_lr=True,
        warmup_epochs=3,

        # --- 损失权重 ---
        box=7.5,
        cls=0.5,
        dfl=1.5,

        # --- 训练策略 ---
        epochs=200,
        patience=50,

        # --- 数据增强 (航拍适配) ---
        mosaic=1.0,
        close_mosaic=30,
        mixup=0.0,
        copy_paste=0.0,
        degrees=25.0,
        scale=0.3,
        translate=0.1,
        fliplr=0.5,
        erasing=0.1,
        hsv_h=0.015,
        hsv_s=0.5,
        hsv_v=0.4,

        # --- 正则化 ---
        dropout=0.0,
    )

    # =========================================================
    # 循环执行实验
    # =========================================================
    print(f"\n{'=' * 70}")
    print(f"  YOLO11-SAFE 消融实验: 共 {len(experiments)} 组")
    print(f"{'=' * 70}")

    for i, exp in enumerate(experiments):
        print(f"\n{'=' * 70}")
        print(f"  实验 {i + 1}/{len(experiments)}: {exp['name']}")
        print(f"  描述: {exp['desc']}")
        print(f"  配置: {exp['yaml']}")
        print(f"{'=' * 70}\n")

        model = YOLO(exp["yaml"])
        model.load("yolo11n.pt")

        # 合并公共参数和实验特定参数
        train_kwargs = dict(common_kwargs)
        train_kwargs["name"] = exp["name"]

        # 透传改进参数 (模型架构 + 损失 + 类别均衡 + 训练策略)
        override_keys = (
            "scale_aware_boost", "use_saciou", "saciou_lambda",
            "cls_pw", "copy_paste", "epochs", "imgsz", "batch",
        )
        for k in override_keys:
            if k in exp:
                train_kwargs[k] = exp[k]

        model.train(**train_kwargs)
        torch.cuda.empty_cache()

    print(f"\n{'=' * 70}")
    print(f"  所有消融实验已全部执行完毕！")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
