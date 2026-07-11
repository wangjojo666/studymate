import { expect, test } from "@playwright/test";
import fs from "node:fs/promises";

test("unauthenticated course access redirects to login", async ({ page }) => {
  await page.goto("/courses");

  await expect(page).toHaveURL(/\/login\?redirect=.*courses/);
  await expect(page.getByRole("button", { name: "登录" })).toBeVisible();
});

test("mobile navigation, keyboard access, URL state, and course switching stay in sync", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await page.getByRole("textbox", { name: "账号邮箱" }).fill("demo@studymate.local");
  await page.getByRole("textbox", { name: "密码" }).fill("studymate-demo");
  await page.getByRole("textbox", { name: "密码" }).press("Enter");
  await expect(page).toHaveURL(/\/$/);

  const firstCourse = await createCourseViaApi(page, `E2E Keyboard A ${Date.now()}`);
  const secondCourse = await createCourseViaApi(page, `E2E Keyboard B ${Date.now()}`);

  const menuButton = page.getByRole("button", { name: "打开主导航" });
  await expect(menuButton).toBeVisible();
  await menuButton.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("navigation", { name: "移动端主导航" })).toBeVisible();

  await page.goto("/courses");
  const firstCourseLink = page.getByRole("link", { name: new RegExp(firstCourse.name) });
  await expect(firstCourseLink).toBeVisible();
  await firstCourseLink.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: firstCourse.name })).toBeVisible();

  await page.getByRole("tab", { name: "AI 问答" }).click();
  await expect(page).toHaveURL(new RegExp(`/courses/${firstCourse.id}\\?tab=qa$`));
  await page.getByRole("tab", { name: "专项练习" }).click();
  await expect(page).toHaveURL(new RegExp(`/courses/${firstCourse.id}\\?tab=practice$`));
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`/courses/${firstCourse.id}\\?tab=qa$`));
  await expect(page.getByRole("tab", { name: "AI 问答" })).toHaveAttribute("aria-selected", "true");

  await page.evaluate(async ({ courseId }) => {
    const app = document.querySelector("#app").__vue_app__;
    await app.config.globalProperties.$router.push(`/courses/${courseId}?tab=docs`);
  }, { courseId: secondCourse.id });
  await expect(page.getByRole("heading", { name: secondCourse.name })).toBeVisible();
  await expect(page.getByRole("heading", { name: firstCourse.name })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "资料库" })).toHaveAttribute("aria-selected", "true");
});

test("course study workflow", async ({ page }, testInfo) => {
  const courseName = `E2E C++ ${Date.now()}`;
  const notesPath = testInfo.outputPath("polymorphism-notes.txt");
  await fs.writeFile(
    notesPath,
    [
      "虚函数可以通过动态绑定实现运行时多态。",
      "当基类指针指向派生类对象并调用被重写的虚函数时，程序会在运行期选择派生类实现。",
      "学习时要区分函数重载、函数重写和虚函数表。"
    ].join("\n"),
    "utf-8"
  );

  await page.goto("/login");
  await page.getByRole("textbox", { name: "账号邮箱" }).fill("demo@studymate.local");
  await page.getByRole("textbox", { name: "密码" }).fill("studymate-demo");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/$/);

  await page.goto("/courses");
  await page.getByRole("button", { name: "新建课程" }).click();
  await page.getByPlaceholder("例如：高等数学").fill(courseName);
  await page.locator(".el-dialog textarea").fill("Playwright 自动化课程");
  await page.getByRole("button", { name: "保存" }).click();
  await expect(page.getByRole("heading", { name: courseName })).toBeVisible();
  await page.getByRole("heading", { name: courseName }).click();

  await expect(page.getByRole("heading", { name: courseName })).toBeVisible();
  await page.locator("input[type=file]").first().setInputFiles(notesPath);
  const documentItem = page.locator(".document-item").filter({ hasText: "polymorphism-notes.txt" });
  await expect(documentItem).toContainText("已入库", { timeout: 30_000 });
  await expect(documentItem).toContainText("最近任务");

  await page.getByRole("tab", { name: "AI 问答" }).click();
  await page.getByPlaceholder("例如：第六章空间解析几何的重点是什么？").fill("虚函数为什么能实现运行时多态？");
  await page.getByRole("button", { name: "提问" }).click();
  await expect(page.locator(".answer").last()).toContainText("虚函数", { timeout: 30_000 });
  await page.locator(".source-strip button").first().click();
  await expect(page.getByText("来源片段")).toBeVisible();
  await expect(page.getByLabel("来源片段").getByText("polymorphism-notes.txt")).toBeVisible();
  await page.keyboard.press("Escape");

  await page.getByRole("tab", { name: "专项练习" }).click();
  await page.getByRole("button", { name: "生成" }).click();
  await expect(page.locator(".practice-card").first()).toBeVisible({ timeout: 30_000 });
  await page.locator(".practice-card textarea").first().fill("概念混淆");
  await page.getByRole("button", { name: "标记答错" }).first().click();
  await expect(page.getByText("已记录错因")).toBeVisible({ timeout: 30_000 });

  await page.getByRole("tab", { name: "学习诊断" }).click();
  await expect(page.getByRole("heading", { name: "总体掌握度" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "薄弱知识点" })).toBeVisible();
});

test("report export button triggers a PDF blob download", async ({ page }) => {
  await loginAsDemo(page);
  const course = await createCourseViaApi(page, `E2E Report ${Date.now()}`);

  await page.goto("/reports");
  await page.locator(".report-actions .el-select").click();
  await page.locator(".el-select-dropdown__item").filter({ hasText: course.name }).click();
  const exportButton = page.locator(".report-actions").getByRole("button", { name: "导出报告", exact: true });
  await expect(exportButton).toBeEnabled();

  const downloadPromise = page.waitForEvent("download");
  await exportButton.click();
  const download = await downloadPromise;

  expect(download.suggestedFilename()).toMatch(/learning-report\.pdf$/);
});

test("cpp analysis shows local compile was not executed in disabled mode", async ({ page }) => {
  await loginAsDemo(page);
  const course = await createCourseViaApi(page, `E2E CPP Disabled ${Date.now()}`);

  await page.goto(`/courses/${course.id}?tab=cpp`);
  await page
    .getByPlaceholder("可选：粘贴自己的答案，系统会判断可能的错误和遗漏考点")
    .fill("#include <iostream>\nint main(){ std::cout << 1; return 0; }");
  await page.getByRole("button", { name: "分析代码" }).click();

  await expect(
    page.getByRole("alert").getByText("当前处于安全演示模式，未执行本地编译运行。")
  ).toBeVisible();
  await expect(page.getByText("未执行本地编译命令")).toBeVisible();
});

async function loginAsDemo(page) {
  await page.goto("/login");
  await page.getByRole("textbox", { name: "账号邮箱" }).fill("demo@studymate.local");
  await page.getByRole("textbox", { name: "密码" }).fill("studymate-demo");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/$/);
}

async function createCourseViaApi(page, name) {
  const token = await page.evaluate(() => window.localStorage.getItem("studymate_access_token"));
  const response = await page.request.post("/api/courses", {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name,
      description: "Playwright API seeded course"
    }
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}
