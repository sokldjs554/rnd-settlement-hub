"use client";

import { api, ApiError, setToken } from "@/lib/api";
import type { LoginResponse } from "@/lib/types";
import { Button, Card, FieldError, Input, Label } from "@/components/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

const schema = z.object({
  email: z.string().email("이메일 형식이 아닙니다"),
  password: z.string().min(1, "비밀번호를 입력하세요"),
});
type FormValues = z.infer<typeof schema>;

export default function LoginPage() {
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    setServerError(null);
    try {
      const res = await api<LoginResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify(values),
        retryOn401: false,
      });
      setToken(res.access_token);
      router.replace(res.user.role === "RESEARCHER" ? "/expenses" : "/");
    } catch (e) {
      setServerError(e instanceof ApiError ? e.message : "로그인에 실패했습니다.");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <Card className="w-full max-w-sm">
        <h1 className="mb-1 text-lg font-bold">RnD Settlement Hub</h1>
        <p className="mb-5 text-sm text-slate-500">R&D 정산 관제 시스템에 로그인하세요.</p>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <div>
            <Label htmlFor="email">이메일</Label>
            <Input id="email" type="email" placeholder="you@company.kr" {...register("email")} />
            <FieldError message={errors.email?.message} />
          </div>
          <div>
            <Label htmlFor="password">비밀번호</Label>
            <Input id="password" type="password" {...register("password")} />
            <FieldError message={errors.password?.message} />
          </div>
          {serverError && <p className="text-sm text-red-600">{serverError}</p>}
          <Button type="submit" disabled={isSubmitting} className="w-full justify-center">
            {isSubmitting ? "로그인 중…" : "로그인"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
