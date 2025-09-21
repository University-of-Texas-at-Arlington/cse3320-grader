#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# CSE3320 Project-1 Autograder
# - Runs `make qemu-nox`
# - Drives xv6 I/O with pexpect
# - Scores per spec: Section I (80) + Section II (20) = 100
#
# Usage:
#   python3 grade_proj1.py --timeout 120
#
import argparse, os, sys, time, re, json, pathlib
import pexpect

PROMPT_ORIG = r"\$ "       # original sh prompt
PROMPT_XVSH = r"xvsh> "    # xvsh prompt

def spawn_qemu(timeout):
    # 若你的 Makefile 用的目标不同，可改为 "make qemu" 或在环境里设置 QEMUEXTRA
    return pexpect.spawn("/bin/bash", ["-lc", "make qemu-nox"], encoding="utf-8", timeout=timeout)

def expect_re(child, pattern, timeout, where=""):
    child.expect(pattern, timeout=timeout)

def sendline(child, s):
    child.sendline(s)

def now():
    return time.time()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=120, help="overall and per-step default timeout (s)")
    args = ap.parse_args()

    total = 0
    score = 0
    results = []
    def add(name, pts, passed, reason=""):
        nonlocal total, score, results
        total += pts
        if passed: score += pts
        results.append({"name": name, "points": pts if passed else 0, "max_points": pts, "passed": passed, "reason": reason})

    pathlib.Path("grade-report").mkdir(exist_ok=True)
    child = spawn_qemu(args.timeout)
    child.logfile = open("grade-report/qemu.log", "w", buffering=1)

    try:
        # 等待原始 shell 提示符
        expect_re(child, PROMPT_ORIG, min(args.timeout, 60), "original prompt")

        # 进入 xvsh
        sendline(child, "xvsh")
        ok_enter = True
        try:
            expect_re(child, PROMPT_XVSH, 10, "xvsh prompt")
        except Exception as e:
            ok_enter = False
        add("Enter xvsh and show xvsh> prompt", 5, ok_enter, "" if ok_enter else "no xvsh> prompt")
        if not ok_enter:
            with open("grade-report/summary.txt","w") as f:
                f.write("FAIL: xvsh did not start. Score = 0/100\n")
            print("==== Project-1 Score ====")
            print("[FAIL] Enter xvsh and show xvsh> prompt: 0/5")
            print("TOTAL: 0/100")
            sys.exit(1)

        # 基本命令可用（echo）
        ok_basic = False
        if ok_enter:
            sendline(child, "echo hello")
            try:
                child.expect(r"hello\r?\n", timeout=5)
                # 回到提示符
                expect_re(child, PROMPT_XVSH, 5, "xvsh prompt after echo")
                ok_basic = True
            except Exception as e:
                ok_basic = False
        add("Basic command works (echo)", 10, ok_basic)

        # 后台 &: 使用 sleep-echo Hello &
        ok_bg = False
        if ok_enter:
            sendline(child, "sleep-echo Hello &")
            try:
                # 1) 后台提示
                child.expect(r"\[pid\s+\d+\]\s+runs as a background process", timeout=4)
                # 2) 立即回到提示符（不阻塞）
                expect_re(child, PROMPT_XVSH, 4, "xvsh prompt immediate")
                # 3) 过几秒后打印 Hello —— 允许尾随空格、只有\r、或无换行
                child.expect(r"Hello(?:[ \t]*\r?\n|[ \t]*\r|$)", timeout=10)
                # 4) 尝试再等提示符（有些实现会立刻回显，有些不会；不作为失败条件）
                try:
                    expect_re(child, PROMPT_XVSH, 3, "prompt after background finished")
                except Exception:
                    pass
                ok_bg = True
            except Exception:
                ok_bg = False
        add("Background (&) runs and later prints Hello", 20, ok_bg)

        # 空命令行：回车应立即再显示 prompt
        ok_empty = False
        if ok_enter:
            sendline(child, "")
            try:
                expect_re(child, PROMPT_XVSH, 3, "empty line prompt")
                ok_empty = True
            except Exception:
                ok_empty = False
        add("Empty command line shows new prompt", 5, ok_empty)

        # 错误命令提示：Cannot run this command a-wrong-cmd
        ok_bad = False
        if ok_enter:
            sendline(child, "a-wrong-cmd arg1 arg2")
            try:
                child.expect(r"Cannot run this command a-wrong-cmd\r?\n", timeout=5)
                expect_re(child, PROMPT_XVSH, 5, "prompt after bad cmd")
                ok_bad = True
            except Exception:
                ok_bad = False
        add("Wrong command message", 10, ok_bad)

        # 管道：ls | wc 应输出三组数字
        ok_pipe = False
        if ok_enter:
            sendline(child, "ls | wc")
            try:
                # 匹配三组数字，中间允许空格或制表符
                child.expect(r"\d+\s+\d+\s+\d+", timeout=5)
                expect_re(child, PROMPT_XVSH, 5, "prompt after pipe")
                ok_pipe = True
            except Exception:
                ok_pipe = False
        add("Pipe (ls | wc) works (3 numbers)", 10, ok_pipe)

        # 重定向：ls > file.txt 然后 ls 确认文件存在
        ok_redir = False
        if ok_enter:
            sendline(child, "rm -f file.txt")   # 确保干净
            sendline(child, "ls > file.txt")
            # 再运行 ls，确认里面出现 file.txt
            sendline(child, "ls")
            try:
                child.expect(r"file\.txt", timeout=5)
                expect_re(child, PROMPT_XVSH, 5, "prompt after redir")
                ok_redir = True
            except Exception:
                ok_redir = False
        add("Redirection (ls > file.txt creates file)", 5, ok_redir)

        # 后台 &: 使用 sleep-echo Hello &
        ok_bg = False
        if ok_enter:
            sendline(child, "sleep-echo Hello &")
            try:
                # 1) 必须出现后台提示
                child.expect(r"\[pid\s+\d+\]\s+runs as a background process", timeout=8)

                # 2) 应该立刻回到提示符（不阻塞）
                expect_re(child, PROMPT_XVSH, 4, "xvsh prompt immediate")

                # 3) 之后若干秒打印 Hello：
                #    - 允许前面带 'xvsh> '（后台完成时刚好打印在提示符后）
                #    - 允许尾随空格
                #    - 允许只有 '\r'、或 '\r?\n'、或干脆没有行尾
                hello_re = r"(?:\r?\n|\r)?(?:xvsh>\s*)?Hello[ \t]*(?:\r?\n|\r|$)"
                child.expect(hello_re, timeout=20)

                # 4) 有的实现不会立刻再给提示符，这里不强制要求
                try:
                    expect_re(child, PROMPT_XVSH, 3, "prompt after background finished")
                except Exception:
                    pass

                ok_bg = True
            except Exception:
                # 便于排查，留一份尾部输出
                try:
                    with open("grade-report/bg_debug_tail.txt", "w") as dbg:
                        dbg.write(child.before[-800:])
                except Exception:
                    pass
                ok_bg = False

        add("Background (&) runs and later prints Hello", 20, ok_bg)        
        

        # Section II: uprog shut (20) —— 需要在原始 $ 下运行
        ok_shutdown = False
        # 从原始 $ 再进一次 xvsh（可选），也可直接在 $ 运行 uprog shut
        try:
            sendline(child, "uprog_shut")
            # 期望 QEMU 很快退出（EOF）
            child.expect(pexpect.EOF, timeout=10)
            ok_shutdown = True
        except Exception:
            ok_shutdown = False
        add("uprog_shut powers off QEMU (EOF observed)", 20, ok_shutdown)

    finally:
        try:
            child.terminate(force=True)
        except Exception:
            pass

    # 输出与归档
    with open("grade-report/summary.txt", "w") as f:
        for r in results:
            f.write(f"{r['name']}: {r['points']}/{r['max_points']} ({'OK' if r['passed'] else 'FAIL'})\n")
        f.write(f"\nTOTAL: {score}/{total}\n")

    print("\n==== Project-1 Score ====")
    for r in results:
        print(f"[{'OK' if r['passed'] else 'FAIL'}] {r['name']}: {r['points']}/{r['max_points']}")
    # 处理总分封顶
    final_score = score
    if final_score > 100:
        final_score = 100
    
    with open("grade-report/summary.txt","w") as f:
        for r in results:
            f.write(f"{r['name']}: {r['points']}/{r['max_points']} ({'OK' if r['passed'] else 'FAIL'})\n")
        f.write(f"\nTOTAL: {final_score}/100\n")
    
    print("\n==== Project-1 Score ====")
    for r in results:
        print(f"[{'OK' if r['passed'] else 'FAIL'}] {r['name']}: {r['points']}/{r['max_points']}")
    print(f"TOTAL: {final_score}/100")
    
    # exit code = 0 仅当满分
    sys.exit(0 if final_score == 100 else 1)

if __name__ == "__main__":
    main()
