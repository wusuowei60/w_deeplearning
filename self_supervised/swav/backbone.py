import torch
from torch import nn


def build_conv3(in_channels, out_channels, stride, padding, groups):
    # default stride=1, groups=1, padding=1
    return nn.Conv2d(
        in_channels,
        out_channels,
        kernel_size=3,
        stride=stride,
        padding=padding,
        groups=groups,
        bias=False,
        dilation=padding,
    )


def build_conv1(in_channels, out_channels, stride):
    return nn.Conv2d(
        in_channels, out_channels, kernel_size=1, stride=stride, bias=False
    )


class BasicBlock(nn.Module):
    expansion = 1
    __constants__ = ["downsample"]

    def __init__(
        self,
        in_channels,
        out_channels,
        stride=1,
        padding=1,
        groups=1,
        base_width=64,
        norm_layer=nn.BatchNorm2d,
    ):
        super().__init__()
        assert groups == 1 and base_width == 64 and padding == 1
        out_channels *= self.expansion
        self.model = nn.Sequential(
            build_conv3(in_channels, out_channels, stride, padding, groups),
            norm_layer(out_channels),
            nn.ReLU(inplace=True),
            build_conv3(out_channels, out_channels, stride=1, padding=1, groups=1),
            norm_layer(out_channels),
        )
        self.final_act = nn.ReLU(inplace=True)

        if stride != 1 or in_channels != out_channels:
            self.downsample = nn.Sequential(
                build_conv1(in_channels, out_channels, stride=stride),
                norm_layer(out_channels),
            )
        else:
            self.downsample = nn.Identity()

    def forward(self, x):
        connection = self.downsample(x)
        out = self.model(x)
        out += connection
        return self.final_act(out)


class Bottleneck(nn.Module):
    expansion = 4
    __constants__ = ["downsample"]

    def __init__(
        self,
        in_channels,
        out_channels,
        stride=1,
        padding=1,
        groups=1,
        base_width=64,
        norm_layer=nn.BatchNorm2d,
    ):
        super().__init__()
        hid_channels = int(out_channels * base_width / 64) * groups
        out_channels *= self.expansion
        self.model = nn.Sequential(
            build_conv1(in_channels, hid_channels, stride=1),
            norm_layer(in_channels),
            nn.ReLU(inplace=True),
            build_conv3(hid_channels, hid_channels, stride, padding, groups),
            norm_layer(hid_channels),
            nn.ReLU(inplace=True),
            build_conv1(hid_channels, out_channels, stride=1),
            norm_layer(out_channels),
        )
        self.final_act = nn.ReLU(inplace=True)

        if stride != 1 or in_channels != out_channels:
            self.downsample = nn.Sequential(
                build_conv1(in_channels, out_channels, stride=stride),
                norm_layer(out_channels),
            )
        else:
            self.downsample = nn.Identity()

    def forward(self, x):
        connection = self.downsample(x)
        out = self.model(x)
        out += connection
        return self.final_act(out)


class ResNet(nn.Module):
    def __init__(
        self,
        # ------ For building blocks ------
        block,
        block_nums,
        padding=1,
        groups=1,
        base_width=64,
        norm_layer=nn.BatchNorm2d,
        replace_stride_with_dilation=(False, False, False),
        # ------ For init conv layer ------
        in_channels=3,
        widen=1,
        first_conv=True,
        maxpool1=True,
        # ------ For linear projection and prototype tensor ------
        hid_dim=0,
        out_dim=0,
        num_prototypes=None,
        # ------ Other stuff ------
        normalize=False,
        zero_init_residual=False,
        eval_mode=True,
    ):
        super().__init__()
        assert len(replace_stride_with_dilation) == 3
        assert len(block_nums) == 4

        self.block = block
        self.padding = padding
        self.groups = groups
        self.norm_layer = norm_layer
        self.base_width = base_width

        self.zero_init_residual = zero_init_residual
        self.eval_mode = eval_mode

        out_channels = base_width * widen
        init_conv = nn.Sequential(
            # nn.ConstantPad2d(1, 0.0),
            nn.Conv2d(
                in_channels,
                out_channels,
                kernel_size=7,
                stride=2,
                padding=3,
                bias=False,
            )
            if first_conv
            else nn.Conv2d(
                in_channels,
                out_channels,
                kernel_size=3,
                stride=1,
                padding=2,
                bias=False,
            ),
            norm_layer(out_channels),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
            if maxpool1
            else nn.MaxPool2d(kernel_size=1, stride=1),
        )

        in_channels = out_channels
        layers = [
            self.make_layer(
                in_channels, out_channels, block_nums[0], stride=1, dilate=False
            )
        ]

        for block_num, dilate in zip(block_nums[1:], replace_stride_with_dilation):
            in_channels = out_channels * block.expansion
            out_channels *= 2
            layers.append(
                self.make_layer(
                    in_channels, out_channels, block_num, stride=2, dilate=dilate
                )
            )

        self.backbone = nn.Sequential(
            init_conv,
            *layers,
        )
        self.final = nn.Sequential(nn.AdaptiveAvgPool2d((1, 1)), nn.Flatten())

        self.l2norm = normalize
        in_dim = out_channels * block.expansion
        if out_dim == 0:
            self.projection_head = None
        elif hid_dim == 0:
            self.projection_head = nn.Linear(in_dim, out_dim)
        else:
            self.projection_head = nn.Sequential(
                nn.Linear(in_dim, hid_dim),
                nn.BatchNorm1d(hid_dim),
                nn.ReLU(inplace=True),
                nn.Linear(hid_dim, out_dim),
            )

        if num_prototypes is None:
            self.prototypes = None
        else:
            self.prototypes = MultiPrototypes(out_dim, num_prototypes)

        self.weight_init()

    def weight_init(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

        # Zero-initialize the last BN in each residual branch,
        # so that the residual branch starts with zeros, and each residual block behaves like an identity.
        # This improves the model by 0.2~0.3% according to https://arxiv.org/abs/1706.02677
        if self.zero_init_residual:
            for m in self.modules():
                if isinstance(m, Bottleneck):
                    nn.init.constant_(m.bn3.weight, 0)
                elif isinstance(m, BasicBlock):
                    nn.init.constant_(m.bn2.weight, 0)

    def make_layer(self, in_channels, out_channels, block_num, stride, dilate=False):
        layers = []
        layers.append(
            self.block(
                in_channels,
                out_channels,
                1 if dilate else stride,
                self.padding,
                self.groups,
                self.base_width,
                self.norm_layer,
            )
        )
        if dilate:
            self.padding *= stride
        in_channels = out_channels * self.block.expansion
        for _ in range(1, block_num):
            layers.append(
                self.block(
                    in_channels,
                    out_channels,
                    stride=1,
                    padding=self.padding,
                    groups=self.groups,
                    base_width=self.base_width,
                    norm_layer=self.norm_layer,
                )
            )
        return nn.Sequential(*layers)

    def forward_backbone(self, x):
        x = self.backbone(x)
        return x if self.eval_mode else self.final(x)

    def forward_head(self, x):
        if self.projection_head is not None:
            x = self.projection_head(x)

        if self.l2norm:
            x = nn.functional.normalize(x, dim=1, p=2)

        if self.prototypes is not None:
            return x, self.prototypes(x)
        else:
            return x

    def forward(self, inputs):
        # inputs: List[Tensor(b x c x h x w)]
        if not isinstance(inputs, list):
            inputs = [inputs]
        _, counts = torch.unique_consecutive(
            torch.tensor([i.shape[-1] for i in inputs])
        )
        start_idx = 0
        outputs = []
        for count in counts:
            _out = torch.cat(inputs[start_idx, start_idx + count], dim=0)
            outputs.append(self.forward_backbone(_out))
            start_idx += count
        return self.forward_head(torch.cat(outputs))


class MultiPrototypes(nn.Module):
    def __init__(self, out_dim, num_prototypes):
        super().__init__()
        self.num_heads = len(num_prototypes)
        for i, k in enumerate(num_prototypes):
            self.add_module("prototypes" + str(i), nn.Linear(out_dim, k, bias=False))

    def forward(self, x):
        out = []
        for i in range(self.num_heads):
            out.append(getattr(self, "prototypes" + str(i))(x))
        return out


def resnet18(**kwargs):
    return ResNet(BasicBlock, [2, 2, 2, 2], **kwargs)


def resnet50(**kwargs):
    return ResNet(Bottleneck, [3, 4, 6, 3], **kwargs)


def resnet50w2(**kwargs):
    return ResNet(Bottleneck, [3, 4, 6, 3], widen=2, **kwargs)


def resnet50w4(**kwargs):
    return ResNet(Bottleneck, [3, 4, 6, 3], widen=4, **kwargs)


def resnet50w5(**kwargs):
    return ResNet(Bottleneck, [3, 4, 6, 3], widen=5, **kwargs)


def test():
    imgs = torch.randn((10, 3, 224, 224))
    model = resnet18()
    print(model.forward_backbone(imgs).shape)


if __name__ == "__main__":
    test()
