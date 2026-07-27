import torchvision.models as models
import torch

print("正在下载并加载 ResNet-50 预训练模型...")
model = models.resnet50(pretrained=True)
print("模型加载成功！")

print("\n原始最后一层：")
print(model.fc)

num_features = model.fc.in_features
model.fc = torch.nn.Linear(num_features, 2)

print("\n修改后的最后一层：")
print(model.fc)

save_path = "D:/肺结节AI项目/models/resnet50_lung_nodule.pth"
torch.save(model.state_dict(), save_path)
print(f"\n模型已保存到：{save_path}")

print("\n正在验证模型能否正常加载...")	
model2 = models.resnet50(pretrained=False)
model2.fc = torch.nn.Linear(num_features, 2)
model2.load_state_dict(torch.load(save_path, map_location='cpu'))
model2.eval()
print("验证成功！模型可以正常加载和使用。")

fake_input = torch.randn(1, 3, 224, 224)

with torch.no_grad():
      output = model2(fake_input)
      probabilities = torch.softmax(output, dim=1)

print(f"\n模拟推理测试：")
print(f"  良性概率：{probabilities[0][0].item():.4f}")
print(f"  恶性概率：{probabilities[0][1].item():.4f}")
print(f"\n第2步全部完成！")