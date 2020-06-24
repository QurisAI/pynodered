from pprint import pprint

from pynodered import node_red, NodeProperty

fn = "function:function(v) {var minimumLength=$('#node-input-number').length?$('#node-input-number').val(" \
     "):this.number; return v.length > minimumLength } "


@node_red(category="Slayer",
          properties=dict(number=NodeProperty("number", value="1", validate='int'),
                          number2=NodeProperty("Number1", value="2", validate='regexp:/^[a-z]+$/'),
                          number3=NodeProperty("Number2", value="2", validate=fn),
                          myname=NodeProperty("Myname", value="2"),
                          script=NodeProperty("Script", value="Yoo", input_type="textarea", rows=10),
                          ms=NodeProperty("MS", value="1", input_type="multi_select", values=['1', '2', '3', "4", "5"],
                                          rows=1),
                          ),
          outputs=4,
          title="My Name",
          inputs=1,
          input_label="Foobar",
          default_output=1,
          color="#BAD",
          output_labels=["One", "Two"],
          label=["number2"],
          label_style="node_label_italic",
          align="center",
          palette_label=None,
          )
def repeat(node, msg):
    # pprint(msg)
    # print(node.node_id)
    # pprint(node.node_data)
    # pprint(node.flow_data)
    # pprint(node.global_data)
    exec(node.script.value, globals(), locals())
    # msg['dashboard']['value'] = 'konijntje'
    # msg['dashboard']['type'] = 'text'
    if 'hits' in node.global_data:
        node.global_data['hits'] += 1
    else:
        node.global_data['hits'] = 1
    out = {}

    x = {'payload': 1}
    y = {'payload': 2}
    z = {'payload': 3}
    node.select_output(2)

    # out['outputs'] = {}
    # out['outputs'][2] = y
    # out['outputs'][1] = z
    # out['outputs'][3] = x
    node.set_status('red', 'ring', 'blablabla aap', 10)
    # pprint(node.__dict__)
    # msg['selected_output'] = 2
    out['payload'] = 'foo'

    return out
    msg['payload'] = msg['payload'] * int(node.number.value)
    if 'blablablabla' not in node.global_data:
        node.global_data['blablablabla'] = "AA"
    else:
        node.global_data['blablablabla'] += "AA"
    if 'blablablabla' not in node.flow_data:
        node.flow_data['blablablabla'] = "BBB"
    else:
        node.flow_data['blablablabla'] += "BBB"
    if 'blablablabla' not in node.node_data:
        node.node_data['blablablabla'] = "CCCC"
    else:
        node.node_data['blablablabla'] += "CCCC"
    msg['payload'] = "Foobar" + node.node_data['blablablabla']

    # pprint(node.node_data)
    if 'output' in node.node_data:
        msg['selected_output'] = (node.node_data['output'] + 1) % 2
    else:
        msg['selected_output'] = 0
    node.node_data['output'] = msg['selected_output']
    pprint(msg)
    # pprint(node.node_data)
    return msg
#
# @node_red(category="pyfuncs")
# def lower_case(node, msg):
#
#     msg['payload'] = msg['payload'].lower()
#     return msg
