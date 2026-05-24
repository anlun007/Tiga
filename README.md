# 彩票分析工具 — Git 上传指南

## 1. 配置 Git 身份（一次性）

打开终端（PowerShell 或 CMD），执行：

```bash
git config --global user.name "你的名字"
git config --global user.email "你的邮箱@example.com"
```

## 2. 在 GitHub 创建远程仓库

1. 打开 https://github.com/new
2. Repository name 填 `lottery-tool`
3. 选 **Private**（推荐）或 Public
4. **不要勾选** "Add a README file"（已有文件）
5. 点击 "Create repository"

创建后会显示一个远程地址，类似：
```
https://github.com/你的用户名/lottery-tool.git
```

## 3. 关联远程仓库并推送

回到终端，进入项目目录：

```bash
cd "C:\Users\33896\Desktop\程序代码\lottery-tool"

# 关联你刚创建的远程仓库（替换为你的地址）
git remote add origin https://github.com/你的用户名/lottery-tool.git

# 推送
git push -u origin master
```

## 4. 后续更新

每次改完代码后：

```bash
git add .
git commit -m "描述这次改了什么"
git push
```

---

## 启动项目

```bash
cd backend_python
pip install -r requirements.txt
python app.py
```

浏览器打开 `http://127.0.0.1:5000`
