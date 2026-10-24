# 素材与高清字形说明

## 渲染方式

号码使用 numerals/contours.json 中经过直边、平行线与折角校正的矢量多边形，在目标分辨率直接渲染。数字6以原图里的短顶帽、长斜线和八角下腹为结构参考，所有车手共用同一套0–9轮廓；9在源图中没有出现，以6旋转180°作为一致风格扩展。

姓名与 RADIO 均使用用户提供的 fonts/Formula1-Bold_web_0.ttf，在目标分辨率渲染 TrueType 矢量轮廓，并沿用原有文字位置、尺寸与颜色。源图中的整段文字和灰度字母只作为字宽、位置的测量与审核材料，保存在 lettering 中。原 RadioRounded 字体保留为历史重建素材。号码仍使用统一矢量数字。

下方 TR 对话框使用用户提供的 fonts/Formula1-Regular_web_0.ttf 常规字体，换行宽度按该字体实际测量。两份 Formula 1 字体随项目资源加载，无需在系统中安装；预览和导出使用相同字体。

中文沿用本机微软雅黑等系统字体回退，其他标题扩展字符沿用 DejaVu 回退。DejaVu 许可见 fonts/LICENSE_DEJAVU.txt。用户提供的 Formula 1 字体不适用 DejaVu 许可，本项目未授予其额外许可。

## 图片素材

logos 中的车队彩色、白色两版徽标，从用户提供的 resource/team_catalog.png 分离；保留各自标识配色。徽标源图约150px宽，高清放大受源素材限制，可上传更清晰的透明 PNG/WebP 队标替换。队标属于各自权利人。

background/reference_panel.png 的斜纹来自源图可见区域；原文字、号码与波形区域被遮罩后补全。顶缘按当前统一强调色施加浅色光。原图完全被文字遮挡的底纹只能推测，不声称恢复未知原始工程。

## 开发工具

tools/extract_numerals.py 与 tools/extract_lettering.py 保留可重复的原图测量及提取过程；tools/build_rounded_font.py 生成可直接渲染的 TrueType 曲线字体。开发时重建字体需要 fonttools、opencv-python 等额外库，日常运行不需要这些开发依赖。

原 resource 文件不被修改。
