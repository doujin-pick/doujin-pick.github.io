/**
 * 同人ピック — グローバル検索 UI
 */
(function () {
  function mount(opts) {
    const input = document.getElementById("global-search");
    const clearBtn = document.getElementById("search-clear");
    if (!input) return;

    const onChange = typeof opts.onChange === "function" ? opts.onChange : () => {};
    const onSubmit = typeof opts.onSubmit === "function" ? opts.onSubmit : onChange;

    function syncClear() {
      if (!clearBtn) return;
      clearBtn.classList.toggle("is-visible", Boolean(input.value));
      clearBtn.hidden = !input.value;
    }

    input.addEventListener("input", () => {
      syncClear();
      onChange(input.value);
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        onSubmit(input.value);
      }
    });

    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        input.value = "";
        syncClear();
        onChange("");
        input.focus();
      });
    }

    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const t = e.target;
        const tag = (t && t.tagName) || "";
        if (tag === "INPUT" || tag === "TEXTAREA" || (t && t.isContentEditable)) return;
        e.preventDefault();
        input.focus();
        input.select();
      }
      if (e.key === "Escape" && document.activeElement === input) {
        if (input.value) {
          input.value = "";
          syncClear();
          onChange("");
        } else {
          input.blur();
        }
      }
    });

    return {
      setValue(v) {
        input.value = v || "";
        syncClear();
      },
      focus() {
        input.focus();
      },
    };
  }

  window.DOJIN_SEARCH = { mount };
})();
