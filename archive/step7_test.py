from step6_detect_nodule import detect_nodule

print("第7步：端到端测试")
print("=" * 40)

image_path = "D:/肺结节AI项目/data/test.jpg"

print(f"正在对图片进行肺结节检测：{image_path}")
print()

result = detect_nodule(image_path)

print("检测结果：")
print(f"  判断结果：{result['class']}")
print(f"  良性概率：{result['benign_prob'] * 100}%")
print(f"  恶性概率：{result['malignant_prob'] * 100}%")
print(f"  热力图路径：{result['heatmap_path']}")
print()
print("第7步完成！整个流程跑通！")