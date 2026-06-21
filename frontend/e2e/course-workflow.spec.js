import { expect, test } from "@playwright/test";
import fs from "node:fs/promises";

test("unauthenticated course access redirects to login", async ({ page }) => {
  await page.goto("/courses");

  await expect(page).toHaveURL(/\/login\?redirect=.*courses/);
  await expect(page.getByRole("button", { name: "登录" })).toBeVisible();
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
  await page.getByPlaceholder("demo@studymate.local").fill("demo@studymate.local");
  await page.getByPlaceholder("studymate-demo").fill("studymate-demo");
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
  await page.getByPlaceholder("demo@studymate.local").fill("demo@studymate.local");
  await page.getByPlaceholder("studymate-demo").fill("studymate-demo");
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
