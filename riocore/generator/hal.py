#!/usr/bin/env python3
#
# hal generator: can resolve logic operation, multiple assignments and invert pins
#


class hal_generator:
    POSTGUI_COMPONENTS = ("pyvcp", "gladevcp", "rio-gui", "qtdragon", "qtvcp", "qtpyvcp", "axisui", "mpg", "vismach", "kinstype", "melfagui", "fanuc_200f", "gmoccapy")
    VIRTUAL_COMPONENTS = ("riov",)
    HAS_INVERTS = {"rio": "-not"}

    def __init__(self):
        self.logic_ids = {}
        self.signals_out = {}
        self.inputs2signals = {}
        self.outputs2signals = {}
        self.expression_cache = {}
        self.hal_logics = {}
        self.hal_calcs = {}
        self.setps = {}
        self.preformated = []
        self.preformated_top = []

    def pin2signal(self, pin, target, signal_name=None):
        if pin.startswith("sig:"):
            return pin.split(":", 2)[-1]
        elif signal_name:
            if pin in self.inputs2signals:
                if self.inputs2signals[pin]["signal"] != signal_name:
                    print(f"ERROR: pin allready exist as signal: {self.inputs2signals[pin]['signal']} (!= {signal_name})")
                    signal = self.inputs2signals[pin]["signal"]
                else:
                    signal = signal_name
            elif pin in self.outputs2signals:
                signal = self.outputs2signals[pin]["signals"][0]
            else:
                signal = signal_name
                self.inputs2signals[pin] = {"signal": signal, "target": target}
        elif pin not in self.inputs2signals:
            if pin in self.outputs2signals:
                signal = self.outputs2signals[pin]["signals"][0]
            else:
                if pin.startswith("func."):
                    signal = f"{pin.replace('.', '_')}"
                else:
                    signal = f"sig_{pin.replace('.', '_')}"
                self.inputs2signals[pin] = {"signal": signal, "target": target}
        else:
            signal = self.inputs2signals[pin]["signal"]
        return signal

    def logic2signal(self, expression, target):
        logic_types = {"AND": 0x100, "OR": 0x200, "XOR": 0x400, "NAND": 0x800, "NOR": 0x1000}
        int_types = {"s+": "scaled_s32_sums", "+": "sum2", "-": "sum2", "*": "mult2", "/": "div2"}

        if expression in self.expression_cache:
            return self.expression_cache[expression]

        if target not in self.logic_ids:
            self.logic_ids[target] = 0
        self.logic_ids[target] += 1
        logic_num = list(self.logic_ids).index(target)
        new_signal = f"{logic_num}.{self.logic_ids[target]}"
        parts = expression.split()
        n_inputs = (len(parts) + 1) // 2
        etype = parts[1].upper()

        if etype in logic_types:
            personality = logic_types[etype] + n_inputs
            fname = f"func.{etype.lower()}_{new_signal}"
            self.hal_logics[fname] = f"0x{personality:x}"
            for in_n in range(n_inputs):
                input_pin = parts[in_n * 2]
                if input_pin.replace(".", "").lstrip("-").isnumeric():
                    self.setp_add(f"{fname}.in-{in_n:02d}", input_pin)
                    continue
                if input_pin[0] == "!":
                    input_pin = self.pin_not(input_pin[1:], target)
                input_signal = self.pin2signal(input_pin, target)
                if f"{fname}.in-{in_n:02d}" not in self.outputs2signals:
                    self.outputs2signals[f"{fname}.in-{in_n:02d}"] = {"signals": [input_signal], "target": target}
                else:
                    self.outputs2signals[f"{fname}.in-{in_n:02d}"]["signals"].append(input_signal)
            output_pin = f"{fname}.{etype.lower()}"
        else:
            personality = int_types[etype]
            if etype == "-":
                fname = f"func.sub2_{new_signal}"
            else:
                fname = f"func.{int_types[etype]}_{new_signal}"
            if personality not in self.hal_calcs:
                self.hal_calcs[personality] = []
            self.hal_calcs[personality].append(fname)
            for in_n in range(n_inputs):
                input_pin = parts[in_n * 2]
                if input_pin.replace(".", "").lstrip("-").isnumeric():
                    self.setp_add(f"{fname}.in{in_n}", input_pin)
                    continue
                input_signal = self.pin2signal(input_pin, target)
                if f"{fname}.in{in_n}" not in self.outputs2signals:
                    self.outputs2signals[f"{fname}.in{in_n}"] = {"signals": [input_signal], "target": target}
                else:
                    self.outputs2signals[f"{fname}.in{in_n}"]["signals"].append(input_signal)

                if etype == "-" and in_n == 1:
                    self.outputs2signals[f"{fname}.gain{in_n}"] = {"signals": -1, "target": target}

            if etype == "s+":
                output_pin = f"{fname}.out-s"
            else:
                output_pin = f"{fname}.out"

        self.expression_cache[expression] = output_pin
        return output_pin

    def text_in_bracket(self, text, right):
        chars = []
        for c in reversed(text[:right]):
            if c != "(":
                chars.append(c)
            else:
                chars.append(c)
                break
        return "".join(reversed(chars))

    def pin_not(self, input_pin, target):
        component = input_pin.split(".", 1)[0]
        if component in self.HAS_INVERTS:
            return f"{input_pin}{self.HAS_INVERTS[component]}"

        if input_pin in self.HAS_INVERTS:
            return f"{input_pin}{self.HAS_INVERTS[input_pin]}"

        if target not in self.logic_ids:
            self.logic_ids[target] = 0
        self.logic_ids[target] += 1
        fname = f"func.not_{input_pin.replace('.', '_')}"
        if "not" not in self.hal_calcs:
            self.hal_calcs["not"] = []
        self.hal_calcs["not"].append(fname)

        input_signal = self.pin2signal(input_pin, target)
        self.outputs2signals[f"{fname}.in"] = {"signals": [input_signal], "target": target}
        return f"{fname}.out"

    def brackets_parser(self, input_pin, output_pin):
        expression = "#"
        while expression:
            expression = ""
            for n, c in enumerate(input_pin):
                if c == ")":
                    expression = self.text_in_bracket(input_pin, n + 1)
                    inside = expression.lstrip("(").rstrip(")")
                    if " " in inside:
                        new_pin = self.logic2signal(inside, output_pin)
                        input_pin = input_pin.replace(expression, new_pin)
                    else:
                        if inside[0] == "!":
                            target = output_pin
                            inside = self.pin_not(inside[1:], target)
                        input_pin = input_pin.replace(expression, inside)
                    break
        return input_pin

    def setp_add(self, output_pin, value):
        if output_pin not in self.setps:
            self.setps[output_pin] = value

    def fmt_add(self, line):
        if isinstance(line, list):
            self.preformated += line
        else:
            self.preformated.append(line)

    def fmt_add_top(self, line):
        if isinstance(line, list):
            self.preformated_top += line
        else:
            self.preformated_top.append(line)

    def net_add(self, input_pin, output_pin, signal_name=None):
        logic = "OR"
        if input_pin[0] == "|":
            logic = "OR"
        elif input_pin[0] == "&":
            logic = "AND"
        elif output_pin in self.signals_out:
            if self.signals_out[output_pin]["expression"][0] == "|":
                logic = "OR"
            elif self.signals_out[output_pin]["expression"][0] == "&":
                logic = "AND"

        if output_pin in self.signals_out:
            self.signals_out[output_pin]["expression"] = f"{self.signals_out[output_pin]['expression']} {logic} {input_pin}"
        else:
            self.signals_out[output_pin] = {"expression": input_pin}

        if signal_name:
            if "name" not in self.signals_out[output_pin]:
                self.signals_out[output_pin]["name"] = signal_name
            elif self.signals_out[output_pin]["name"] != signal_name:
                print(f"ERROR: signalname ({signal_name}) allready set for this input: {self.signals_out['expression']}")

    def net_write(self):
        hal_data = []
        postgui_data = []

        hal_data.append("")
        for line in self.preformated_top:
            hal_data.append(line)

        for output, data in self.signals_out.items():
            cleaned_expression = data["expression"].replace("|", "").replace("&", "")
            input_pin = self.brackets_parser(f"({cleaned_expression})", output)

            input_signal = self.pin2signal(input_pin, output, data.get("name"))

            if output in self.outputs2signals:
                self.outputs2signals[output]["signals"].append(input_signal)
            else:
                self.outputs2signals[output] = {"signals": [input_signal], "target": output}

        hal_data.append("#################################################################################")
        hal_data.append("# logic and calc components")
        hal_data.append("#################################################################################")

        # combine and add logic functions
        func_names = []
        func_personalities = []
        for func, personality in self.hal_logics.items():
            func_names.append(func)
            func_personalities.append(personality)
        hal_data.append(f"loadrt logic names={','.join(func_names)} personality={','.join(func_personalities)}")
        for fname in func_names:
            hal_data.append(f"addf {fname} servo-thread")
        hal_data.append("")

        # combine and add other functions
        func_names = []
        func_personalities = []
        for calc, names in self.hal_calcs.items():
            hal_data.append(f"loadrt {calc} names={','.join(names)}")
            for name in names:
                hal_data.append(f"addf {name} servo-thread")
            hal_data.append("")

        postgui_data.append("#################################################################################")
        postgui_data.append("# networks")
        postgui_data.append("#################################################################################")

        # add networks
        for target in self.signals_out:
            hal_data.append("#################################################################################")
            hal_data.append(f"# {self.signals_out[target]['expression']} --> {target}")
            hal_data.append("#################################################################################")

            for pin, data in self.inputs2signals.items():
                if data["target"] == target and not pin.startswith("func."):
                    component = pin.split(".", 1)[0]
                    if component in self.POSTGUI_COMPONENTS:
                        hal_data.append(f"# net {data['signal']:30s} <= {pin} (in postgui)")
                        postgui_data.append(f"net {data['signal']:30s} <= {pin}")
                    elif component in self.VIRTUAL_COMPONENTS:
                        hal_data.append(f"# net {data['signal']:30s} <= {pin} (virtual pin)")
                    else:
                        hal_data.append(f"net {data['signal']:30s} <= {pin}")

            prefixes = []
            for pin, data in self.outputs2signals.items():
                if data["target"] == target and pin.startswith("func."):
                    prefix = ".".join(pin.split(".")[:-1])
                    if prefix not in prefixes:
                        prefixes.append(prefix)
            for prefix in prefixes:
                # logic inputs
                for pin, data in self.outputs2signals.items():
                    if data["target"] == target and pin.startswith(prefix):
                        if isinstance(data["signals"], int):
                            hal_data.append(f"setp {pin:32s} {data['signals']}")
                            continue
                        for signal in data["signals"]:
                            hal_data.append(f"net {signal:30s} => {pin}")
                # logic outputs
                for pin, data in self.inputs2signals.items():
                    if data["target"] == target and pin.startswith(prefix):
                        hal_data.append(f"net {data['signal']:30s} <= {pin}")

            for pin, data in self.outputs2signals.items():
                component = pin.split(".", 1)[0]
                if data["target"] == target and not pin.startswith("func."):
                    for signal in data["signals"]:
                        if component in self.POSTGUI_COMPONENTS:
                            hal_data.append(f"# net {signal:30s} => {pin} (in postgui)")
                            postgui_data.append(f"net {signal:30s} => {pin}")
                        elif component in self.VIRTUAL_COMPONENTS:
                            hal_data.append(f"# net {signal:30s} => {pin} (virtual pin)")
                        else:
                            hal_data.append(f"net {signal:30s} => {pin}")
            hal_data.append("")
        postgui_data.append("")

        if self.setps:
            hal_data.append("#################################################################################")
            hal_data.append("# setp")
            hal_data.append("#################################################################################")

            postgui_data.append("#################################################################################")
            postgui_data.append("# setp")
            postgui_data.append("#################################################################################")

            for pin, value in self.setps.items():
                signal = self.outputs2signals.get(pin) or self.inputs2signals.get(pin)
                if not signal:
                    component = pin.split(".", 1)[0]
                    if component in self.POSTGUI_COMPONENTS:
                        hal_data.append(f"# setp {pin:30s}   {value:6} (in postgui)")
                        postgui_data.append(f"setp {pin:30s}   {value}")
                    else:
                        hal_data.append(f"setp {pin:30s}   {value}")
                else:
                    hal_data.append(f"# setp {pin:30s}   {value:6} (allready linked to {', '.join(signal.get('signals', [signal.get('signal', '?')]))})")

            hal_data.append("")
            postgui_data.append("")

        hal_data.append("#################################################################################")
        hal_data.append("# preformated")
        hal_data.append("#################################################################################")
        for line in self.preformated:
            hal_data.append(line)

        return (hal_data, postgui_data)


if __name__ == "__main__":
    halg = hal_generator()

    halg.net_add("!rio.input1", "hal.output2")
    halg.net_add("rio.input1", "hal.output1")
    halg.net_add("rio.input1 and !rio.input2", "hal.output3")

    halg.net_add("!pio.input1", "hal.pio_output2")
    halg.net_add("pio.input1", "hal.pio_output1")
    halg.net_add("pio.input1 and !pio.input2", "hal.pio_output3")

    halg.net_add("rio.input2 or pyvcp.input3", "hal.or_out")
    halg.net_add("rio.s32_1 + rio.s32_2 + rio.s32_3", "hal.out-sint")
    halg.net_add("(rio.float_1 * rio.float_2) / (rio.float_3 * rio.float_4)", "hal.out-float")
    halg.net_add("rio.s32_1 - rio.s32_2", "hal.out-sint")

    halg.net_add("|rio.input2", "hal.or_out")
    halg.net_add("rio.input3", "hal.or_out")

    halg.net_add("&rio.input4", "pyvcp.and_out")
    halg.net_add("rio.input5", "pyvcp.and_out")

    halg.net_add("&rio.input8", "pyvcp.complex_out")
    halg.net_add("(sig:existing or rio.input5 or rio.input6) and rio.input7", "pyvcp.complex_out", "my_complex_out")

    halg.net_add("(rio.input5 or rio.input6)", "rio.orout1")
    halg.net_add("(rio.input5 or rio.input6)", "rio.orout2")

    halg.setp_add("pyvcp.outval", "123")
    halg.setp_add("rio.outval", "123")
    halg.setp_add("rio.orout1", "0")
    halg.setp_add("rio.s32_1", "100")

    (hal_data, postgui_data) = halg.net_write()
    print("\n".join(hal_data))
    print("---------------------------------")
    print("\n".join(postgui_data))
