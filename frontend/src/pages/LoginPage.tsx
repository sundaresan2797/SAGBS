import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle, CheckCircle2, Lock } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import logo from "@/assets/sat-logo.jpg";
import { Button } from "@/components/ui/Button";
import { PoweredBy } from "@/components/PoweredBy";
import { InputField } from "@/components/ui/FormField";
import { COMPANY_NAME } from "@/config/company";
import { useAuth } from "@/hooks/useAuth";
import { getErrorMessage } from "@/services/api";

const loginSchema = z.object({
  email: z.string().min(1, "Please enter your email").email("That doesn't look like a valid email"),
  password: z.string().min(1, "Please enter your password"),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export function LoginPage() {
  const { isAuthenticated, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [formError, setFormError] = useState<string | null>(null);
  const notice = (location.state as { notice?: string } | null)?.notice ?? null;

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) });

  if (isAuthenticated) {
    const redirectTo = (location.state as { from?: Location })?.from?.pathname ?? "/dashboard";
    return <Navigate to={redirectTo} replace />;
  }

  const onSubmit = async (values: LoginFormValues) => {
    setFormError(null);
    try {
      await login(values.email, values.password);
      navigate("/dashboard", { replace: true });
    } catch (error) {
      setFormError(getErrorMessage(error, "That email and password don't match. Please try again."));
    }
  };

  return (
    <div className="grid min-h-screen bg-white lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      {/* Brand panel: the logo's own navy ground fills the panel, so the eagle sits on it without a visible box. */}
      <aside className="relative hidden overflow-hidden bg-[#001c49] lg:block">
        <img src={logo} alt="" className="absolute inset-0 h-full w-full object-cover object-center" />
        <div className="absolute inset-0 bg-gradient-to-t from-[#001233] via-[#001233]/40 to-transparent" />
        <div className="absolute inset-x-0 bottom-0 p-12 text-white">
          <h2 className="font-display text-4xl font-bold tracking-tight">{COMPANY_NAME}</h2>
          <p className="mt-3 max-w-md text-base text-blue-100/90">
            One place for your attendance, leave, payslips and tasks.
          </p>
        </div>
      </aside>

      <main className="flex flex-col justify-center px-6 py-10 sm:px-12">
        <div className="mx-auto w-full max-w-sm">
          <div className="mb-8 flex flex-col items-center text-center lg:items-start lg:text-left">
            <img src={logo} alt={`${COMPANY_NAME} logo`} className="mb-4 h-20 w-20 rounded-2xl object-cover shadow-md lg:hidden" />
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-700">{COMPANY_NAME}</p>
            <h1 className="mt-2 font-display text-3xl font-bold text-stone-800">Sign in</h1>
            <p className="mt-1.5 text-sm text-stone-500">Use your work email and password to open your portal.</p>
          </div>

          {notice && (
            <p
              role="status"
              className="mb-4 flex items-start gap-2 rounded-xl bg-brand-50 px-3.5 py-3 text-sm font-medium text-brand-700"
            >
              <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
              {notice}
            </p>
          )}
          <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
            <InputField
              label="Email address"
              type="email"
              autoComplete="username"
              placeholder="you@company.com"
              error={errors.email?.message}
              {...register("email")}
            />
            <InputField
              label="Password"
              type="password"
              autoComplete="current-password"
              placeholder="Your password"
              error={errors.password?.message}
              {...register("password")}
            />

            {formError && (
              <p
                role="alert"
                className="flex items-start gap-2 rounded-xl bg-sunset-50 px-3.5 py-3 text-sm font-medium text-sunset-700"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
                {formError}
              </p>
            )}

            <Button type="submit" isLoading={isSubmitting} className="mt-2 w-full" size="md">
              Sign in
            </Button>
          </form>

          <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-stone-400 lg:justify-start">
            <Lock className="h-3.5 w-3.5" aria-hidden="true" />
            Secure sign-in. Forgot your password? Ask your HR or Admin to reset it.
          </p>

          <p className="mt-8 text-center text-xs text-stone-400 lg:text-left">
            &copy; {new Date().getFullYear()} {COMPANY_NAME}. All rights reserved.
          </p>
          <PoweredBy className="mt-1 text-center lg:text-left" />
        </div>
      </main>
    </div>
  );
}
