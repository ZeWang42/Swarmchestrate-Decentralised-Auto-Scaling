import numpy as np
import matplotlib.pyplot as plt

# ---------------------------
# Global font settings
# ---------------------------
plt.rcParams.update({
    "font.size": 16,
    "axes.labelsize": 16,
    "axes.titlesize": 18,
    "xtick.labelsize": 16,
    "ytick.labelsize": 16,
    "legend.fontsize": 16,
})

# Parameters (scaled to [0,100])
alpha = 30
tau_min = 60
tau_max = 80
beta = 95
c = 1.0
s = 3.0

# rho now in [0,100]
rho = np.linspace(0.0, 100.0, 1000)

p_down = np.zeros_like(rho)
p_up = np.zeros_like(rho)
p_hold = np.zeros_like(rho)

eps = 1e-9

for i, r in enumerate(rho):
    if r < tau_min:
        denom = max(tau_min - r, eps)
        exponent = s * (alpha - r) / denom
        exponent = np.clip(exponent, -50, 50)
        p_down[i] = min(c, np.exp(exponent))
        print(f"DOWN: rho={r:.2f}, exponent={exponent:.2f}, p_down={p_down[i]:.4f}")

    elif r > tau_max:
        denom = max(r - tau_max, eps)
        exponent = s * (r - beta) / denom
        exponent = np.clip(exponent, -50, 50)
        p_up[i] = min(c, np.exp(exponent))

    else:
        p_hold[i] = 1.0

# Plot
plt.figure(figsize=(8, 5))

# Region shading
plt.axvspan(0.0, tau_min, color="tab:blue", alpha=0.15)
plt.axvspan(tau_min, tau_max, color="tab:green", alpha=0.15)
plt.axvspan(tau_max, 100.0, color="tab:red", alpha=0.15)

# Curves
plt.plot(rho, p_down, color="tab:blue", linewidth=2.5)
plt.plot(rho, p_hold, color="tab:green", linestyle="--", linewidth=2.5)
plt.plot(rho, p_up, color="tab:red", linewidth=2.5)

# Vertical lines
plt.axvline(alpha, color="gray", linestyle=":", linewidth=1.5)
plt.axvline(tau_min, color="gray", linestyle=":", linewidth=1.5)
plt.axvline(tau_max, color="gray", linestyle=":", linewidth=1.5)
plt.axvline(beta, color="gray", linestyle=":", linewidth=1.5)

# X ticks (now in 0–100 scale)
plt.xticks(
    [alpha, tau_min, tau_max, beta, 100],
    [r"$\alpha$", r"$\tau_{\min}$", r"$\tau_{\max}$", r"$\beta$", r"$100$"]
)

# Y ticks
plt.yticks([0, c], [r"$0$", r"$c$"])

plt.xlabel(r"Utilisation ($\rho$)")
plt.ylabel("Probability")
plt.title("DAS Scaling Probability Function")

plt.xlim(0.0, 100.0)
plt.ylim(0.0, c + 0.05)

plt.grid(True, alpha=0.3)

# Region labels
plt.text(10, 0.9, "DOWN", color="tab:blue")
plt.text(65, 0.9, "HOLD", color="tab:green")
plt.text(85, 0.9, "UP", color="tab:red")

plt.tight_layout()
plt.savefig("das_probability.pdf", bbox_inches="tight")
plt.show()