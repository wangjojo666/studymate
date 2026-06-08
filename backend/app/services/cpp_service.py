from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.llm_service import call_llm


OFFLINE_CPP_PROVIDER = "rule/offline"


@dataclass(frozen=True)
class CppPattern:
    name: str
    pattern: str
    exam_hint: str


CPP_PATTERNS = [
    CppPattern("类与对象", r"\b(class|struct)\s+[A-Za-z_]\w*", "关注访问控制、成员函数和对象生命周期。"),
    CppPattern("继承与派生", r"\b(class|struct)\s+\w+\s*:\s*(public|protected|private)?\s*\w+", "常考基类/派生类构造顺序、访问权限和替换原则。"),
    CppPattern("虚函数与多态", r"\bvirtual\b|\boverride\b", "常考动态绑定、基类指针/引用调用派生类重写函数。"),
    CppPattern("纯虚函数与抽象类", r"=\s*0\s*;", "注意抽象类不能直接实例化，派生类必须实现纯虚函数。"),
    CppPattern("友元", r"\bfriend\b", "友元可访问私有成员，但不属于类成员，破坏封装时要谨慎。"),
    CppPattern("运算符重载", r"\boperator\s*(?:[+\-*/%=<>!&|^~\[\](),]+|new|delete)", "常考返回值类型、成员/非成员形式和 const 正确性。"),
    CppPattern("模板", r"\btemplate\s*<", "关注类型参数、函数模板/类模板实例化和编译期多态。"),
    CppPattern("STL 容器", r"\b(std::)?(vector|map|set|queue|stack|list|deque|string)\s*<", "注意迭代器失效、复杂度和容器适用场景。"),
    CppPattern("指针与引用", r"(\w+\s*[*&]\s*\w+)|(\w+\s*[*&]\s*[),=])", "常考空指针、悬垂引用、传参语义和资源释放。"),
    CppPattern("构造与析构", r"\b~[A-Za-z_]\w*\s*\(|\b[A-Za-z_]\w*\s*::\s*[A-Za-z_]\w*\s*\(", "关注初始化列表、析构顺序和基类析构函数是否 virtual。"),
]


def analyze_cpp_code(
    course_name: str,
    problem_text: str,
    code_text: str,
    user_code: str = "",
) -> dict:
    reference_code = code_text.strip()
    submitted_code = user_code.strip()
    target_code = submitted_code or reference_code
    combined = "\n".join(part for part in (problem_text.strip(), reference_code, submitted_code) if part)

    exam_points = _detect_exam_points(combined)
    error_diagnosis = _diagnose_cpp_errors(target_code, reference_code if submitted_code else "")
    explanation = _offline_explanation(problem_text, reference_code, submitted_code, exam_points, error_diagnosis)
    llm_response = _llm_cpp_explanation(course_name, problem_text, reference_code, submitted_code, exam_points)
    provider = llm_response.used_provider if llm_response else OFFLINE_CPP_PROVIDER
    if llm_response:
        explanation = llm_response.content

    return {
        "summary": _summary(exam_points, error_diagnosis, submitted_code),
        "provider": provider,
        "exam_points": exam_points,
        "explanation": explanation,
        "similar_exercises": _similar_exercises(exam_points),
        "error_diagnosis": error_diagnosis,
    }


def _detect_exam_points(text: str) -> list[dict]:
    points: list[dict] = []
    for item in CPP_PATTERNS:
        match = re.search(item.pattern, text, flags=re.I | re.S)
        if not match:
            continue
        evidence = _line_containing(text, match.group(0))
        points.append(
            {
                "name": item.name,
                "evidence": evidence[:180],
                "exam_hint": item.exam_hint,
            }
        )
    if not points and text.strip():
        points.append(
            {
                "name": "基础语法与程序阅读",
                "evidence": text.strip()[:180],
                "exam_hint": "先判断输入输出、变量含义、控制流和边界条件。",
            }
        )
    return points[:8]


def _diagnose_cpp_errors(code: str, reference_code: str = "") -> list[dict]:
    issues: list[dict] = []
    if not code.strip():
        return [
            {
                "level": "info",
                "title": "未提供用户代码",
                "detail": "填写用户代码后，系统会检查语法风险、考点遗漏和与参考代码的差异。",
            }
        ]

    if re.search(r"\b(cout|cin|endl)\b", code) and not re.search(r"using\s+namespace\s+std|std::", code):
        issues.append(_issue("warning", "std 命名空间缺失", "代码使用 cout/cin/endl，但没有 std:: 前缀或 using namespace std。"))
    if re.search(r"\bvector\s*<|\bstring\b", code) and "std::" not in code and "using namespace std" not in code:
        issues.append(_issue("warning", "STL 名称空间风险", "vector/string 等 STL 类型通常需要 std:: 前缀或 using namespace std。"))
    if re.search(r"\bnew\b", code) and not re.search(r"\bdelete\b|unique_ptr|shared_ptr", code):
        issues.append(_issue("warning", "资源释放风险", "代码出现 new，但没有对应 delete 或智能指针，可能造成内存泄漏。"))
    if re.search(r"\bvirtual\b", code) and re.search(r"\bclass\s+\w+", code) and not re.search(r"virtual\s+~\w+\s*\(", code):
        issues.append(_issue("suggestion", "基类析构函数建议设为 virtual", "含虚函数的基类如果通过基类指针删除派生类对象，析构函数应声明为 virtual。"))
    if re.search(r"\bclass\s+\w+[\s\S]*?}\s*(?!;)", code):
        issues.append(_issue("error", "类定义后可能缺少分号", "C++ 的 class/struct 定义结束后需要以分号结尾。"))
    if re.search(r"=\s*0\s*;", code) and re.search(r"\bnew\s+\w+\s*\(", code):
        issues.append(_issue("warning", "抽象类实例化风险", "如果 new 的类型仍含纯虚函数，会导致抽象类不能实例化。"))

    if reference_code:
        issues.extend(_compare_with_reference(code, reference_code))

    if not issues:
        issues.append(_issue("ok", "未发现明显问题", "规则检查没有发现高风险错误，仍建议用编译器和样例数据验证。"))
    return issues[:8]


def _compare_with_reference(user_code: str, reference_code: str) -> list[dict]:
    issues: list[dict] = []
    expected_points = {point["name"] for point in _detect_exam_points(reference_code)}
    actual_points = {point["name"] for point in _detect_exam_points(user_code)}
    for missing in sorted(expected_points - actual_points):
        issues.append(
            _issue(
                "warning",
                f"可能遗漏考点：{missing}",
                "参考代码包含该考点，但用户代码中未识别到对应写法，请检查是否漏写关键语法。",
            )
        )
    if "虚函数与多态" in expected_points and "override" not in user_code and "virtual" in user_code:
        issues.append(_issue("suggestion", "建议补充 override", "派生类重写虚函数时加 override，可让编译器检查签名是否一致。"))
    return issues


def _offline_explanation(
    problem_text: str,
    reference_code: str,
    submitted_code: str,
    exam_points: list[dict],
    error_diagnosis: list[dict],
) -> str:
    code = submitted_code or reference_code
    lines = [line.rstrip() for line in code.splitlines() if line.strip()]
    point_lines = "\n".join(f"- {point['name']}：{point['exam_hint']}" for point in exam_points)
    issue_lines = "\n".join(f"- [{item['level']}] {item['title']}：{item['detail']}" for item in error_diagnosis)
    structure = _code_structure(lines)
    problem_part = f"\n题目理解：{problem_text.strip()}\n" if problem_text.strip() else ""
    return (
        f"{problem_part}"
        "## 代码结构\n"
        f"{structure}\n\n"
        "## 执行思路\n"
        "先识别类、函数和主流程，再判断对象创建、函数调用和输出结果；遇到虚函数时按动态绑定规则分析。\n\n"
        "## 考点识别\n"
        f"{point_lines or '- 暂未识别到典型 C++ 考点。'}\n\n"
        "## 错误诊断\n"
        f"{issue_lines}"
    )


def _llm_cpp_explanation(
    course_name: str,
    problem_text: str,
    reference_code: str,
    submitted_code: str,
    exam_points: list[dict],
):
    code = submitted_code or reference_code
    if not code.strip():
        return None
    messages = [
        {
            "role": "system",
            "content": (
                "你是 C++ 程序设计课程助教。请解释代码、识别考点、指出用户代码错误，"
                "不要编造题目外条件，输出中文 Markdown。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"课程：{course_name}\n题目：{problem_text}\n"
                f"参考/题目代码：\n```cpp\n{reference_code[:8000]}\n```\n"
                f"用户代码：\n```cpp\n{submitted_code[:8000]}\n```\n"
                f"规则识别考点：{[point['name'] for point in exam_points]}\n"
                "请按“代码解释、考点、易错点、同类训练方向、用户代码问题”组织。"
            ),
        },
    ]
    return call_llm(messages, temperature=0.1)


def _similar_exercises(exam_points: list[dict]) -> list[dict]:
    names = [point["name"] for point in exam_points] or ["基础语法与程序阅读"]
    exercises: list[dict] = []
    for index, name in enumerate(names[:3], start=1):
        exercises.append(
            {
                "title": f"同类练习 {index}：{name}",
                "prompt": _exercise_prompt(name),
                "expected_focus": name,
            }
        )
    return exercises


def _exercise_prompt(name: str) -> str:
    prompts = {
        "继承与派生": "设计 Base/Derived 两个类，说明 public 继承下成员访问权限和构造顺序，并写出程序输出。",
        "虚函数与多态": "给出基类指针指向派生类对象的代码，判断调用哪个函数，并解释动态绑定条件。",
        "友元": "编写一个类和一个 friend 函数，说明 friend 如何访问私有成员以及它为什么不是成员函数。",
        "运算符重载": "为一个 Complex 类重载 operator+，比较成员函数和非成员函数写法的差异。",
        "模板": "写一个函数模板 maxValue，并说明模板实例化时类型参数如何推导。",
    }
    return prompts.get(name, f"围绕“{name}”写一段 15 行以内 C++ 代码，要求说明输出结果和常见错误。")


def _summary(exam_points: list[dict], error_diagnosis: list[dict], submitted_code: str) -> str:
    point_names = "、".join(point["name"] for point in exam_points) or "基础语法"
    risky = [item for item in error_diagnosis if item["level"] in {"error", "warning"}]
    target = "用户代码" if submitted_code else "题目代码"
    return f"{target}主要涉及 {point_names}；规则检查发现 {len(risky)} 个需要关注的问题。"


def _code_structure(lines: list[str]) -> str:
    class_count = sum(1 for line in lines if re.search(r"\b(class|struct)\s+\w+", line))
    function_count = sum(1 for line in lines if re.search(r"\w+\s+\w+\s*\([^;]*\)\s*(const)?\s*(override)?\s*[{;]", line))
    main_count = sum(1 for line in lines if re.search(r"\bmain\s*\(", line))
    return f"- 类/结构体数量约 {class_count} 个\n- 函数或成员函数声明约 {function_count} 个\n- main 入口 {'存在' if main_count else '未识别'}"


def _line_containing(text: str, needle: str) -> str:
    for line in text.splitlines():
        if needle and needle in line:
            return line.strip()
    return needle.strip()


def _issue(level: str, title: str, detail: str) -> dict:
    return {"level": level, "title": title, "detail": detail}
